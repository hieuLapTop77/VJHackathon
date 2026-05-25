"""
kaggle/src/trainer.py — Train & evaluate 6 models.
Inductive preprocessing: split FIRST, then fit imputation/encoding on Train only.
"""
import os
import sys
import time
import json
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
    mean_absolute_error,
)

_KAGGLE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_KAGGLE_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from kaggle.src.config import (
    OUTPUT_DIR, DATA_PROCESSED,
    FEATURE_COLS, TARGET_COL,
    TEST_SIZE, VALID_SIZE, RANDOM_STATE,
    XGB_PARAMS, LGB_PARAMS, CB_PARAMS,
    RF_PARAMS, GB_PARAMS, MLP_PARAMS,
)


def compute_metrics(y_true, y_pred) -> dict:
    return {
        "mape": float(mean_absolute_percentage_error(y_true, y_pred) * 100),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae":  float(mean_absolute_error(y_true, y_pred)),
        "r2":   float(r2_score(y_true, y_pred)),
    }


def _imputation_stats(series: pd.Series) -> str:
    if series.dtype in ["int64", "float64"]:
        return "median" if series.dropna().skew() >= 0.5 else "mean"
    return "mode"


def prepare_data(df_clean: pd.DataFrame, feature_cols: list) -> tuple:
    print("\n" + "=" * 60)
    print("INDUCTIVE PREPROCESSING (no data leakage)")
    print("=" * 60)

    target = TARGET_COL
    df = df_clean.copy()

    null_target = df[target].isnull().sum()
    if null_target > 0:
        print(f"[prepare] Dropping {null_target:,} rows with null target")
        df = df.dropna(subset=[target])

    X_trainval, X_test, y_trainval, y_test = train_test_split(
        df, df[target], test_size=TEST_SIZE, random_state=RANDOM_STATE,
    )
    valid_ratio = VALID_SIZE / (1 - TEST_SIZE)
    X_train, X_valid, y_train, y_valid = train_test_split(
        X_trainval, y_trainval, test_size=valid_ratio, random_state=RANDOM_STATE,
    )

    print(f"[prepare] Split: Train={len(X_train):,} | Valid={len(X_valid):,} | Test={len(X_test):,}")

    imputation_values = {}
    print("\n[prepare] Inductive numeric imputation (fit on Train only):")
    for col in X_train.select_dtypes(include=[np.number]).columns:
        strategy = _imputation_stats(X_train[col])
        fill_val = X_train[col].median() if strategy == "median" else X_train[col].mean()
        imputation_values[col] = {"strategy": strategy, "fill_value": fill_val}
        X_train[col] = X_train[col].fillna(fill_val)
        X_valid[col] = X_valid[col].fillna(fill_val)
        X_test[col]  = X_test[col].fillna(fill_val)
        print(f"  [impute] {col}: {strategy}={fill_val:,.2f}")

    encoders = {}
    print("\n[prepare] Inductive LabelEncoder (fit on Train only):")
    for raw_col, enc_col in [
        ("fare_family",  "fare_family_enc"),
        ("fare_category","fare_category_enc"),
        ("route",        "route_enc"),
    ]:
        if raw_col not in X_train.columns:
            continue
        le = LabelEncoder()
        X_train[enc_col] = le.fit_transform(X_train[raw_col].astype(str))
        X_valid[enc_col] = X_valid[raw_col].astype(str).map(
            lambda v: le.transform([v])[0] if v in le.classes_ else -1
        )
        X_test[enc_col]  = X_test[raw_col].astype(str).map(
            lambda v: le.transform([v])[0] if v in le.classes_ else -1
        )
        encoders[raw_col] = le
        print(f"  [encode] {raw_col}: {len(le.classes_)} classes")

    available = [c for c in feature_cols if c in X_train.columns]
    X_train_feat = X_train[available].fillna(0)
    X_valid_feat = X_valid[available].fillna(0)
    X_test_feat  = X_test[available].fillna(0)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    joblib.dump(encoders, f"{OUTPUT_DIR}/label_encoders.pkl")
    joblib.dump(imputation_values, f"{OUTPUT_DIR}/imputation_values.pkl")

    print(f"\n[prepare] Feature matrix: {X_train_feat.shape[1]} features")
    print(f"[prepare] Encoders saved -> {OUTPUT_DIR}/label_encoders.pkl")

    return (
        X_train_feat, X_valid_feat, X_test_feat,
        y_train.reset_index(drop=True),
        y_valid.reset_index(drop=True),
        y_test.reset_index(drop=True),
        encoders, imputation_values, available,
    )


def train_xgboost(X_train, y_train, X_valid, y_valid, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training XGBoost...")
    print("-" * 40)
    t0 = time.time()
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.set_params(early_stopping_rounds=50, eval_metric="mape")
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=100)
    elapsed = time.time() - t0
    metrics = compute_metrics(y_test, model.predict(X_test))
    metrics["time_sec"] = elapsed
    metrics["model"] = "XGBoost"
    print(f"XGBoost done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def train_lightgbm(X_train, y_train, X_valid, y_valid, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training LightGBM...")
    print("-" * 40)
    t0 = time.time()
    model = lgb.LGBMRegressor(**LGB_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_valid, y_valid)],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
    )
    elapsed = time.time() - t0
    metrics = compute_metrics(y_test, model.predict(X_test))
    metrics["time_sec"] = elapsed
    metrics["model"] = "LightGBM"
    print(f"LightGBM done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def train_catboost(X_train, y_train, X_valid, y_valid, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training CatBoost...")
    print("-" * 40)
    t0 = time.time()
    model = CatBoostRegressor(**CB_PARAMS)
    model.fit(X_train, y_train, eval_set=(X_valid, y_valid), early_stopping_rounds=50)
    elapsed = time.time() - t0
    metrics = compute_metrics(y_test, model.predict(X_test))
    metrics["time_sec"] = elapsed
    metrics["model"] = "CatBoost"
    print(f"CatBoost done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def train_random_forest(X_train, y_train, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training Random Forest...")
    print("-" * 40)
    t0 = time.time()
    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(X_train, y_train)
    elapsed = time.time() - t0
    metrics = compute_metrics(y_test, model.predict(X_test))
    metrics["time_sec"] = elapsed
    metrics["model"] = "RandomForest"
    print(f"Random Forest done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def train_gradient_boosting(X_train, y_train, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training Gradient Boosting (sklearn)...")
    print("-" * 40)
    t0 = time.time()
    model = GradientBoostingRegressor(**GB_PARAMS)
    model.fit(X_train, y_train)
    elapsed = time.time() - t0
    metrics = compute_metrics(y_test, model.predict(X_test))
    metrics["time_sec"] = elapsed
    metrics["model"] = "GradientBoosting"
    print(f"Gradient Boosting done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def train_mlp(X_train, y_train, X_valid, y_valid, X_test, y_test):
    print("\n" + "-" * 40)
    print("Training MLP Neural Network...")
    print("-" * 40)
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_vl = scaler.transform(X_valid)
    X_te = scaler.transform(X_test)
    t0 = time.time()
    model = MLPRegressor(**MLP_PARAMS)
    model.fit(X_tr, y_train)
    elapsed = time.time() - t0
    model._scaler = scaler
    metrics = compute_metrics(y_test, model.predict(X_te))
    metrics["time_sec"] = elapsed
    metrics["model"] = "MLP"
    print(f"MLP done in {elapsed:.1f}s | MAPE: {metrics['mape']:.2f}% | R2: {metrics['r2']:.4f}")
    return model, metrics


def predict_with_model(model, X):
    scaler = getattr(model, "_scaler", None)
    if scaler is not None:
        X = scaler.transform(X)
    return model.predict(X)


def train_all(df_clean: pd.DataFrame, feature_cols: list):
    print("\n" + "=" * 60)
    print("TRAINING 6 ML MODELS")
    print("=" * 60)

    (X_train, X_valid, X_test,
     y_train, y_valid, y_test,
     encoders, imputation_values,
     feature_names) = prepare_data(df_clean, feature_cols)

    results = []
    models_dict = {}

    model_xgb, m = train_xgboost(X_train, y_train, X_valid, y_valid, X_test, y_test)
    models_dict["XGBoost"] = model_xgb
    results.append(m)

    model_lgb, m = train_lightgbm(X_train, y_train, X_valid, y_valid, X_test, y_test)
    models_dict["LightGBM"] = model_lgb
    results.append(m)

    model_cb, m = train_catboost(X_train, y_train, X_valid, y_valid, X_test, y_test)
    models_dict["CatBoost"] = model_cb
    results.append(m)

    model_rf, m = train_random_forest(X_train, y_train, X_test, y_test)
    models_dict["RandomForest"] = model_rf
    results.append(m)

    model_gb, m = train_gradient_boosting(X_train, y_train, X_test, y_test)
    models_dict["GradientBoosting"] = model_gb
    results.append(m)

    model_mlp, m = train_mlp(X_train, y_train, X_valid, y_valid, X_test, y_test)
    models_dict["MLP"] = model_mlp
    results.append(m)

    results_df = pd.DataFrame(results).sort_values("mape")
    print("\n" + "=" * 60)
    print("MODEL COMPARISON (Test Set)")
    print("=" * 60)
    print(results_df[["model", "mape", "rmse", "mae", "r2", "time_sec"]].to_string(index=False))

    best = results_df.iloc[0]
    print(f"\nBest Model: {best['model']} | MAPE: {best['mape']:.2f}% | R2: {best['r2']:.4f}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name, model in models_dict.items():
        safe = name.lower().replace(" ", "_")
        joblib.dump(model, f"{OUTPUT_DIR}/{safe}_model.pkl")
    joblib.dump(models_dict, f"{OUTPUT_DIR}/all_models.pkl")
    joblib.dump(models_dict["MLP"]._scaler, f"{OUTPUT_DIR}/mlp_scaler.pkl")

    results_df.to_csv(f"{OUTPUT_DIR}/model_comparison.csv", index=False)

    with open(f"{OUTPUT_DIR}/feature_names.txt", "w") as f:
        f.write("\n".join(feature_names))

    best_model_name = str(best["model"])
    final_report = {
        "best_model": best_model_name,
        "best_mape":  round(float(best["mape"]), 4),
        "best_rmse":  round(float(best["rmse"]), 2),
        "best_mae":   round(float(best["mae"]), 2),
        "best_r2":    round(float(best["r2"]), 6),
        "all_models_ranked": results_df.to_dict("records"),
        "preprocessing": "inductive (fit on Train only)",
        "training_summary": {
            "n_features":   len(feature_names),
            "train_rows":   len(X_train),
            "valid_rows":   len(X_valid),
            "test_rows":    len(X_test),
        },
    }
    with open(f"{OUTPUT_DIR}/final_report.json", "w") as f:
        json.dump(final_report, f, indent=2)

    print(f"\n[trainer] All artifacts saved to: {OUTPUT_DIR}/")
    return (
        models_dict, results_df,
        X_train, X_valid, X_test,
        y_train, y_valid, y_test,
        feature_names, best_model_name,
    )


if __name__ == "__main__":
    from kaggle.src.data_loader import load
    from kaggle.src.preprocessor import preprocess
    df = load()
    df_clean, feats = preprocess(df)
    train_all(df_clean, feats)

"""
kaggle/scripts/predict.py — Inference script using trained models.

Usage:
    python kaggle/scripts/predict.py --model xgboost --input data.csv --output predictions.csv
"""
import argparse
import os
import sys

_KAGGLE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_KAGGLE_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import joblib
import pandas as pd
import numpy as np

from kaggle.src.config import OUTPUT_DIR, FEATURE_COLS


MODEL_MAP = {
    "xgboost":         "xgboost_model.pkl",
    "lightgbm":         "lightgbm_model.pkl",
    "catboost":         "catboost_model.pkl",
    "randomforest":     "random_forest_model.pkl",
    "gradientboosting": "gradient_boosting_model.pkl",
    "mlp":              "mlp_model.pkl",
}


def load_model(name: str):
    filename = MODEL_MAP.get(name.lower())
    if not filename:
        raise ValueError(f"Unknown model: {name}. Available: {list(MODEL_MAP.keys())}")
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found: {path}")
    return joblib.load(path)


def predict(model, X: pd.DataFrame) -> np.ndarray:
    scaler = getattr(model, "_scaler", None)
    if scaler is not None:
        X = scaler.transform(X)
    return model.predict(X)


def main():
    parser = argparse.ArgumentParser(description="Predict ticket prices using trained models")
    parser.add_argument("--model",   default="xgboost",  help=f"Model name: {list(MODEL_MAP.keys())}")
    parser.add_argument("--input",   required=True,      help="Input CSV with features")
    parser.add_argument("--output",  default="predictions.csv", help="Output CSV path")
    parser.add_argument("--models-dir", default=None,     help="Override models directory")
    args = parser.parse_args()

    if args.models_dir:
        global OUTPUT_DIR
        OUTPUT_DIR = args.models_dir

    print(f"[predict] Loading model: {args.model}")
    model = load_model(args.model)

    print(f"[predict] Loading input: {args.input}")
    df = pd.read_csv(args.input)
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    X = df[available].fillna(0)

    if missing:
        print(f"[predict] WARNING -- missing features (will use 0): {missing}")

    print(f"[predict] Input shape: {X.shape} | Features: {len(available)}/{len(FEATURE_COLS)}")

    preds = predict(model, X)

    out = df.copy()
    out["predicted_price"] = preds
    out.to_csv(args.output, index=False)
    print(f"[predict] Saved {len(preds):,} predictions -> {args.output}")


if __name__ == "__main__":
    main()

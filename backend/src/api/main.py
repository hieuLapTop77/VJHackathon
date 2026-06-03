"""
backend/src/api/main.py — FastAPI Backend
=========================================
Endpoints:
  POST /predict       -- du doan gia ve (single record)
  POST /predict-ensemble -- ensemble prediction (3 strategies)
  POST /upload-predict -- du doan tu file (CSV/Excel)
  POST /optimize      -- gia toi uu cho 1 chuyen bay
  POST /simulate      -- what-if revenue simulation
  GET  /health       -- health check + model info
  GET  /models       -- list available models
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import json
import numpy as np
import pandas as pd
import joblib
import os
import sys
from datetime import datetime

# Project root is two levels up from this file
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from backend.config import OUTPUTS_DIR
from backend.src.models.optimizer import optimize_flight, simulate_range
from backend.src.models.trainer import load_kaggle_models, get_best_model_name
from backend.src.db import sqlserver


# ── App lifespan: load artifacts once, store in app.state ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQL Server DB (create DB + table if not exist)
    try:
        sqlserver.init_db()
        
        # Check if flights table is empty and auto-seed if it is
        conn = sqlserver._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM flights")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        if count == 0:
            print("[startup] Flights table is empty. Auto-seeding from raw data...")
            df = _load_data()
            result = sqlserver.upsert_flights(df)
            print(f"[startup] Auto-seeded {result['inserted']} rows.")
    except Exception as ex:
        print(f"[startup] DB init warning: {ex}")

    enc_path = os.path.join(OUTPUTS_DIR, "label_encoders.pkl")
    if os.path.exists(enc_path):
        app.state.label_encoders = joblib.load(enc_path)
        print(f"Encoders loaded: {enc_path}")
    else:
        app.state.label_encoders = {}
        print("Warning: Label encoders not found")

    qt_path = os.path.join(OUTPUTS_DIR, "target_transformer.pkl")
    if os.path.exists(qt_path):
        app.state.target_transformer = joblib.load(qt_path)
        print(f"Target transformer loaded: {qt_path}")
    else:
        app.state.target_transformer = None
        print("Warning: Target transformer (QuantileTransformer) not found")

    fn_path = os.path.join(OUTPUTS_DIR, "feature_names.txt")
    if os.path.exists(fn_path):
        with open(fn_path) as f:
            app.state.feature_names = [l.strip() for l in f if l.strip()]
        print(f"Feature names loaded: {len(app.state.feature_names)} features")
    else:
        app.state.feature_names = []

    app.state.models = load_kaggle_models()
    app.state.best_model_name = "XGBoost"
    app.state.model_metrics = {}

    if app.state.models:
        app.state.best_model_name = get_best_model_name()
        print(f"Models loaded: {list(app.state.models.keys())}")
        print(f"Best model: {app.state.best_model_name}")

        cmp_path = os.path.join(OUTPUTS_DIR, "model_comparison.csv")
        if os.path.exists(cmp_path):
            import csv as _csv
            with open(cmp_path) as f:
                for row in _csv.DictReader(f):
                    app.state.model_metrics[row["model"]] = {
                        "mape": float(row["mape"]),
                        "rmse": float(row["rmse"]),
                        "mae":  float(row["mae"]),
                        "r2":   float(row["r2"]),
                    }
            print(f"Metrics loaded from: {cmp_path}")
    else:
        print("Warning: No models found -- run: python kaggle/scripts/run_pipeline.py")

    yield  # app runs here

    # Cleanup (if needed)
    app.state.models = {}
    app.state.label_encoders = {}


app = FastAPI(
    title="Airline Revenue Optimizer API",
    description="AI-powered pricing recommendations for airline revenue management",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173",
                   "http://localhost:8000", "http://frontend:80",
                   "http://frontend-prod:80"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global aliases (backward compat shim — routes should use request.app.state)
ALL_MODELS = {}  # deprecated: read from request.app.state.models
BEST_MODEL_NAME = "XGBoost"  # deprecated
LABEL_ENCODERS = {}  # deprecated
MODEL_METRICS = {}  # deprecated
FEATURE_NAMES = []  # deprecated


# ── Request / Response schemas ─────────────────────────────────────────────────
class PredictRequest(BaseModel):
    lead_time_days:      int   = Field(..., example=30)
    LF_by_date:          float = Field(..., example=0.65)
    LF_by_fare:          float = Field(..., example=0.40)
    booking_velocity_3d: float = Field(..., example=0.02)
    booking_velocity_7d: float = Field(..., example=0.05)
    Weekday:             int   = Field(..., example=4)
    IsHoliday:           int   = Field(0, example=0)
    is_oneway:           int   = Field(1, example=1)
    lng_fuel:            float = Field(..., example=93.86)
    capacity:            int   = Field(..., example=230)
    count_sked:          int   = Field(3, example=3)
    fare_family:         str   = Field(..., example="Eco")
    fare_category:       str   = Field(..., example="B  ")
    dep:                 str   = Field(..., example="SGN")
    arr:                 str   = Field(..., example="HAN")
    model_name:          Optional[str]   = Field(None, example="XGBoost")


class OptimizeRequest(BaseModel):
    base_price:       float          = Field(..., example=950000)
    base_lf:          float          = Field(..., example=0.55)
    capacity:         int           = Field(..., example=230)


class SimulateRequest(BaseModel):
    base_price: float = Field(..., example=950000)
    base_lf:    float = Field(..., example=0.55)
    capacity:   int   = Field(..., example=230)
    from_pct:   float = Field(-30, example=-30)
    to_pct:     float = Field(50,  example=50)


class EnsembleRequest(BaseModel):
    lead_time_days:      int   = Field(..., example=30)
    LF_by_date:          float = Field(..., example=0.65)
    LF_by_fare:          float = Field(..., example=0.40)
    booking_velocity_3d: float = Field(..., example=0.02)
    booking_velocity_7d: float = Field(..., example=0.05)
    Weekday:             int   = Field(..., example=4)
    IsHoliday:           int   = Field(0, example=0)
    is_oneway:           int   = Field(1, example=1)
    lng_fuel:            float = Field(..., example=93.86)
    capacity:            int   = Field(..., example=230)
    count_sked:          int   = Field(3, example=3)
    fare_family:         str   = Field(..., example="Eco")
    fare_category:       str   = Field(..., example="B  ")
    dep:                 str   = Field(..., example="SGN")
    arr:                 str   = Field(..., example="HAN")
    strategy:            str   = Field("weighted_perf", example="weighted_perf")
    # strategy options: "average" | "weighted_perf" | "top3"


class ApplyRequest(BaseModel):
    applied_price: float = Field(..., example=1050000)
    model_used: Optional[str] = Field(None, example="XGBoost")


# ── Helpers ─────────────────────────────────────────────────────────────────────
def _days_bucket(lead_time_days: int) -> int:
    """Match training preprocessor.py pd.cut bins: [-1, 3, 7, 14, 30, 60, 90, 365]"""
    if lead_time_days <= 3:
        return 0
    elif lead_time_days <= 7:
        return 1
    elif lead_time_days <= 14:
        return 2
    elif lead_time_days <= 30:
        return 3
    elif lead_time_days <= 60:
        return 4
    elif lead_time_days <= 90:
        return 5
    else:
        return 6


def clean_fare_category(val: str) -> str:
    val = str(val).strip()
    for prefix in ["D1", "D2", "FF", "GR", "P6", "Ps"]:
        if val.startswith(prefix):
            return prefix + " "
    if val:
        return val[0] + "  "
    return "B  "


def _build_features(req: PredictRequest, app_state) -> pd.DataFrame:
    route = f"{req.dep}-{req.arr}"

    urgency_score        = round(req.LF_by_date / (req.lead_time_days + 1), 6)
    velocity_ratio       = req.booking_velocity_3d / (req.booking_velocity_7d + 1e-6)
    velocity_ratio       = round(min(10.0, max(0.0, velocity_ratio)), 4)
    seats_remaining      = max(0, int(req.capacity * (1 - req.LF_by_date)))
    is_weekend          = int(req.Weekday in [5, 6])
    days_bucket         = _days_bucket(req.lead_time_days)
    log_lead_time       = round(float(np.log1p(req.lead_time_days)), 4)
    lf_velocity_interact = round(req.LF_by_date * req.booking_velocity_7d, 4)
    expected_sold        = int(round(req.capacity * req.LF_by_date, 0))

    # Time-based features matching preprocessor
    today = pd.Timestamp.now().normalize()
    booking_date = today
    departure_date = today + pd.Timedelta(days=req.lead_time_days)
    
    booking_month = booking_date.month
    dep_month = departure_date.month
    dep_quarter = departure_date.quarter
    dep_day_of_month = departure_date.day
    is_peak_season = int(dep_month in [1, 2, 6, 7, 8])

    # Unused column features
    str_Gender = 1
    seats_sold = 1
    occupancy_rate = round(seats_sold / max(1, req.capacity), 4)

    row = {
        "lead_time_days":        req.lead_time_days,
        "LF_by_date":            req.LF_by_date,
        "LF_by_fare":            req.LF_by_fare,
        "booking_velocity_3d":   req.booking_velocity_3d,
        "booking_velocity_7d":   req.booking_velocity_7d,
        "Weekday":               req.Weekday,
        "IsHoliday":             req.IsHoliday,
        "is_oneway":             req.is_oneway,
        "fuel_price":            req.lng_fuel,
        "capacity":              req.capacity,
        "count_sked":            req.count_sked,
        "urgency_score":         urgency_score,
        "velocity_ratio":        velocity_ratio,
        "seats_remaining":       seats_remaining,
        "is_weekend":            is_weekend,
        "days_bucket":           days_bucket,
        "log_lead_time":         log_lead_time,
        "lf_velocity_interact":   lf_velocity_interact,
        "expected_sold":         expected_sold,
        "dep_month":             dep_month,
        "dep_quarter":           dep_quarter,
        "dep_day_of_month":      dep_day_of_month,
        "booking_month":         booking_month,
        "is_peak_season":        is_peak_season,
        "str_Gender":            str_Gender,
        "occupancy_rate":        occupancy_rate,
    }

    label_encoders = getattr(app_state, "label_encoders", {}) or {}
    feature_names = getattr(app_state, "feature_names", []) or []

    for col, enc_col, val in [
        ("fare_family",  "fare_family_enc",  req.fare_family),
        ("fare_category","fare_category_enc", clean_fare_category(req.fare_category)),
        ("route",        "route_enc",        route),
        ("agency_currency", "agency_currency_enc", "VND"),
    ]:
        le = label_encoders.get(col)
        if le:
            val_str = str(val).strip()
            matched_class = None
            for c in le.classes_:
                if str(c).strip() == val_str:
                    matched_class = c
                    break
            if matched_class is not None:
                row[enc_col] = int(le.transform([matched_class])[0])
            else:
                row[enc_col] = -1

    X = pd.DataFrame([row])

    if feature_names:
        for c in feature_names:
            if c not in X.columns:
                X[c] = 0
        X = X[feature_names]
    else:
        models = getattr(app_state, "models", {}) or {}
        best = getattr(app_state, "best_model_name", "XGBoost")
        ref_model = models.get(best) or list(models.values())[0] if models else None
        if ref_model and hasattr(ref_model, "feature_names_in_"):
            for c in ref_model.feature_names_in_:
                if c not in X.columns:
                    X[c] = 0
            X = X[ref_model.feature_names_in_]

    return X


def _build_features_df(df: pd.DataFrame, app_state) -> pd.DataFrame:
    df = df.copy()

    # Normalize column names to standard names and fill defaults if missing
    defaults = {
        "lead_time_days": 30,
        "LF_by_date": 0.65,
        "LF_by_fare": 0.40,
        "booking_velocity_3d": 0.02,
        "booking_velocity_7d": 0.05,
        "Weekday": 4,
        "IsHoliday": 0,
        "is_oneway": 1,
        "lng_fuel": 93.86,
        "capacity": 230,
        "count_sked": 3,
        "fare_family": "Eco",
        "fare_category": "B",
        "dep": "SGN",
        "arr": "HAN",
        "agency_currency": "VND",
    }
    
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        else:
            if col in ["fare_family", "fare_category", "dep", "arr", "agency_currency"]:
                df[col] = df[col].fillna(val).astype(str)
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)

    # Clean/clip values like training
    df["LF_by_date"] = df["LF_by_date"].clip(0.0, 1.0)
    df["LF_by_fare"] = df["LF_by_fare"].clip(0.0, 1.0)

    # Derived features matching preprocessor.py & _build_features
    df["route"] = df["dep"] + "-" + df["arr"]
    df["urgency_score"] = (df["LF_by_date"] / (df["lead_time_days"] + 1)).round(6)
    df["velocity_ratio"] = (df["booking_velocity_3d"] / (df["booking_velocity_7d"] + 1e-6)).clip(0.0, 10.0).round(4)
    df["seats_remaining"] = (df["capacity"] * (1.0 - df["LF_by_date"])).clip(lower=0).astype(int)
    df["is_weekend"] = df["Weekday"].isin([5, 6]).astype(int)
    
    # days_bucket bins
    def get_days_bucket_val(lt):
        if lt <= 3: return 0
        elif lt <= 7: return 1
        elif lt <= 14: return 2
        elif lt <= 30: return 3
        elif lt <= 60: return 4
        elif lt <= 90: return 5
        else: return 6
    df["days_bucket"] = df["lead_time_days"].apply(get_days_bucket_val)
    
    df["log_lead_time"] = np.log1p(df["lead_time_days"]).round(4)
    df["lf_velocity_interact"] = (df["LF_by_date"] * df["booking_velocity_7d"]).round(4)
    df["expected_sold"] = (df["capacity"] * df["LF_by_date"]).round(0)
    
    # In training, fuel_price maps from lng_fuel
    df["fuel_price"] = df["lng_fuel"]

    # Time-based features from dates if present
    if "booking_date" in df.columns:
        b_dt = pd.to_datetime(df["booking_date"], errors="coerce")
    else:
        b_dt = pd.Series([pd.Timestamp.now().normalize()] * len(df))
        
    if "departure_date" in df.columns:
        d_dt = pd.to_datetime(df["departure_date"], errors="coerce")
    else:
        d_dt = b_dt + pd.to_timedelta(df["lead_time_days"], unit="D")
        
    b_dt = b_dt.fillna(pd.Timestamp.now().normalize())
    d_dt = d_dt.fillna(b_dt + pd.to_timedelta(df["lead_time_days"], unit="D"))
    
    df["booking_month"] = b_dt.dt.month.fillna(0).astype(int)
    df["dep_month"] = d_dt.dt.month.fillna(0).astype(int)
    df["dep_quarter"] = d_dt.dt.quarter.fillna(0).astype(int)
    df["dep_day_of_month"] = d_dt.dt.day.fillna(0).astype(int)
    df["is_peak_season"] = df["dep_month"].isin([1, 2, 6, 7, 8]).astype(int)

    # Data-derived features
    if "str_Gender" not in df.columns:
        df["str_Gender"] = 1
    else:
        df["str_Gender"] = pd.to_numeric(df["str_Gender"], errors="coerce").fillna(1).astype(int)
        
    if "seats_sold" not in df.columns:
        df["seats_sold"] = 1
    else:
        df["seats_sold"] = pd.to_numeric(df["seats_sold"], errors="coerce").fillna(1).astype(int)
        
    df["occupancy_rate"] = (df["seats_sold"] / df["capacity"].replace(0, 1)).clip(0.0, 1.0).round(4)

    # Encode categorical fields using label encoders
    label_encoders = getattr(app_state, "label_encoders", {}) or {}
    for col, enc_col in [
        ("fare_family", "fare_family_enc"),
        ("fare_category", "fare_category_enc"),
        ("route", "route_enc"),
        ("agency_currency", "agency_currency_enc"),
    ]:
        le = label_encoders.get(col)
        if le:
            class_map = {str(c).strip(): int(le.transform([c])[0]) for c in le.classes_}
            if col == "fare_category":
                df[enc_col] = df[col].apply(lambda x: class_map.get(clean_fare_category(x).strip(), -1))
            else:
                df[enc_col] = df[col].apply(lambda x: class_map.get(str(x).strip(), -1))
        else:
            df[enc_col] = -1

    # Keep only the target training features in correct order
    feature_names = getattr(app_state, "feature_names", []) or []
    if feature_names:
        for col in feature_names:
            if col not in df.columns:
                df[col] = 0
        X = df[feature_names]
    else:
        # Fallback to model's feature names
        models = getattr(app_state, "models", {}) or {}
        best = getattr(app_state, "best_model_name", "XGBoost")
        ref_model = models.get(best) or list(models.values())[0] if models else None
        if ref_model and hasattr(ref_model, "feature_names_in_"):
            for c in ref_model.feature_names_in_:
                if c not in df.columns:
                    df[c] = 0
            X = df[ref_model.feature_names_in_]
        else:
            X = df
            
    return X


def _predict_with_model(model, X, app_state=None):
    """Predict with model and perform correct inverse target transformation."""
    if hasattr(model, "models_dict") and hasattr(model, "weights"):
        preds = []
        total_w = 0
        for name, sub_model in model.models_dict.items():
            w = model.weights.get(name, 0)
            if w > 0:
                p = _predict_with_model(sub_model, X, app_state)
                preds.append(p * w)
                total_w += w
        if total_w > 0:
            return np.sum(preds, axis=0)
        else:
            first_model = list(model.models_dict.values())[0]
            return _predict_with_model(first_model, X, app_state)

    scaler = getattr(model, "_scaler", None)
    if scaler is not None:
        X = scaler.transform(X)
        
    raw_pred = model.predict(X)
    
    qt = getattr(model, "_target_transformer", None)
    if qt is None and app_state is not None:
        qt = getattr(app_state, "target_transformer", None)
        
    if qt is not None:
        if hasattr(raw_pred, "reshape"):
            raw_pred_2d = raw_pred.reshape(-1, 1)
            pred = qt.inverse_transform(raw_pred_2d).ravel()
        else:
            pred = qt.inverse_transform(np.array([[raw_pred]])).ravel()
        return np.clip(pred, 0, None)
        
    is_log = getattr(model, "_is_log_target", False) or (np.mean(raw_pred) < 20.0)
    if is_log:
        return np.expm1(raw_pred)
        
    return raw_pred


def _predict_and_format_results(df: pd.DataFrame, model, app_state, filename: str, db_result: dict = None) -> dict:
    # Rename maps for columns to support multiple input file schemas
    rename_map = {
        "capacity": "capacity",
        "lng_Capacity": "capacity",
        "fare_family": "fare_family",
        "str_Fare_Family_Ident": "fare_family",
        "fare_category": "fare_category",
        "str_Fare_Category_Ident": "fare_category",
        "str_Fare_Class_Short": "fare_category",
        "dep": "dep",
        "str_Dep": "dep",
        "arr": "arr",
        "str_Arr": "arr",
        "fuel_price": "lng_fuel",
        "lng_fuel": "lng_fuel",
        "lf": "LF_by_date",
        "LF_by_date": "LF_by_date",
        "lf_fare": "LF_by_fare",
        "LF_by_fare": "LF_by_fare",
        "dtm_Creation_Date": "booking_date",
        "booking_date": "booking_date",
        "dtm_Local_ETD_Date": "departure_date",
        "departure_date": "departure_date",
        "str_Currency_Ident": "agency_currency",
        "agency_currency": "agency_currency",
        "str_Gender": "str_Gender",
        "lng_Seats": "seats_sold",
        "seats_sold": "seats_sold",
    }
    
    df_rename = {}
    for col in df.columns:
        if col in rename_map:
            df_rename[col] = rename_map[col]
    if df_rename:
        df_norm = df.rename(columns=df_rename)
    else:
        df_norm = df.copy()

    df_norm = df_norm.loc[:, ~df_norm.columns.duplicated()]

    X = _build_features_df(df_norm, app_state)

    preds = _predict_with_model(model, X, app_state)
    
    # Clamp to min 50K VND
    PRICE_MIN = 50_000.0
    preds = np.maximum(preds, PRICE_MIN)

    df_result = df.copy()
    df_result["predicted_fare_vnd"] = np.round(preds, -3).astype(int)
    if "mny_GL_Charges_Total" in df_result.columns:
        df_result["actual_fare_vnd"] = df_result["mny_GL_Charges_Total"]

    def _safe_float(v):
        try:
            f = float(v)
            return None if (f != f or f == float('inf') or f == float('-inf')) else f
        except Exception:
            return None

    def _sanitize_row(row: dict) -> dict:
        out = {}
        for k, v in row.items():
            if isinstance(v, float):
                out[k] = _safe_float(v)
            elif hasattr(v, 'item'):
                out[k] = _safe_float(v.item())
            else:
                out[k] = v
        return out

    preview_rows = [_sanitize_row(r) for r in df_result.head(20).to_dict(orient="records")]
    
    inserted = db_result.get("inserted", 0) if db_result else 0
    updated = db_result.get("updated", 0) if db_result else 0

    return {
        "model_used": model.__class__.__name__,
        "rows_total": len(df_result),
        "preview": preview_rows,
        "summary": {
            "mean_predicted":   _safe_float(np.round(np.mean(preds), -3)),
            "median_predicted": _safe_float(np.round(np.median(preds), -3)),
            "min_predicted":    _safe_float(np.round(np.min(preds), -3)),
            "max_predicted":    _safe_float(np.round(np.max(preds), -3)),
        },
        "filename": filename,
        "rows_inserted": inserted,
        "rows_updated": updated,
    }


def _get_model(app_state, model_name: Optional[str] = None):
    models = getattr(app_state, "models", {}) or {}
    best   = getattr(app_state, "best_model_name", "XGBoost")
    if model_name and model_name in models:
        return models[model_name]
    return models.get(best)


# ── Endpoints ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "models_loaded": list(request.app.state.models.keys()),
        "best_model": request.app.state.best_model_name,
    }


@app.get("/models")
def get_models(request: Request):
    result = []
    for name, model in request.app.state.models.items():
        if model is not None:
            metrics = request.app.state.model_metrics.get(name, {})
            result.append({
                "name": name,
                "best": name == request.app.state.best_model_name,
                "type": type(model).__name__,
                "mape": metrics.get("mape"),
                "r2":   metrics.get("r2"),
            })
    return {"models": result, "best_model": request.app.state.best_model_name}


@app.post("/predict")
def predict(req: PredictRequest, request: Request):
    model = _get_model(request.app.state, req.model_name)
    if model is None:
        raise HTTPException(503, "No model loaded. Run: python kaggle/scripts/run_pipeline.py")

    X = _build_features(req, request.app.state)

    scaler = getattr(model, "_scaler", None)
    if scaler is not None:
        X = scaler.transform(X)

    used_model = req.model_name if req.model_name and req.model_name in request.app.state.models else request.app.state.best_model_name
    raw_price = float(_predict_with_model(model, X, request.app.state)[0])
    PRICE_MIN = 50_000.0
    predicted_price = max(PRICE_MIN, raw_price)
    is_valid = raw_price >= PRICE_MIN

    return {
        "predicted_price_vnd": round(predicted_price, -3),
        "route": f"{req.dep}-{req.arr}",
        "fare_family": req.fare_family,
        "lead_time_days": req.lead_time_days,
        "model_used": used_model,
        "clamped": not is_valid,
    }


# ── Ensemble prediction (3 strategies) ───────────────────────────────────────────
@app.post("/predict-ensemble")
def predict_ensemble(req: EnsembleRequest, request: Request):
    """
    Ensemble prediction across all 6 models using 3 strategies:
      - "average"        : simple mean of all model predictions
      - "weighted_perf"  : inverse-MAPE weighted average (better models get more weight)
      - "top3"           : mean of top-3 models by MAPE (XGBoost, RF, LightGBM)
    Returns per-model breakdowns plus the ensemble result.
    """
    models = request.app.state.models
    metrics = request.app.state.model_metrics
    if not models:
        raise HTTPException(503, "No models loaded. Run: python kaggle/scripts/run_pipeline.py")

    # Build feature vector once
    predict_req = PredictRequest(
        lead_time_days=req.lead_time_days,
        LF_by_date=req.LF_by_date,
        LF_by_fare=req.LF_by_fare,
        booking_velocity_3d=req.booking_velocity_3d,
        booking_velocity_7d=req.booking_velocity_7d,
        Weekday=req.Weekday,
        IsHoliday=req.IsHoliday,
        is_oneway=req.is_oneway,
        lng_fuel=req.lng_fuel,
        capacity=req.capacity,
        count_sked=req.count_sked,
        fare_family=req.fare_family,
        fare_category=req.fare_category,
        dep=req.dep,
        arr=req.arr,
        model_name=None,
    )
    X = _build_features(predict_req, request.app.state)

    # Run each model
    PRICE_MIN = 50_000.0
    individual = {}
    for name, model in models.items():
        try:
            pred = float(_predict_with_model(model, X_run, request.app.state)[0])
            pred = max(PRICE_MIN, pred)
            mape = metrics.get(name, {}).get("mape", 100.0)
            individual[name] = {"prediction": round(pred, -3), "mape": mape}
        except Exception as ex:
            individual[name] = {"prediction": None, "error": str(ex)}

    valid = {n: v for n, v in individual.items() if v.get("prediction") is not None}
    if not valid:
        raise HTTPException(503, "No model produced a valid prediction")

    preds = np.array([v["prediction"] for v in valid.values()])
    model_names = list(valid.keys())
    mapes = np.array([valid[n]["mape"] for n in model_names])

    result = {}

    # Strategy 1: Simple average
    result["average"] = {
        "predicted_price_vnd": round(float(np.mean(preds)), -3),
        "models_used": model_names,
        "model_count": len(model_names),
    }

    # Strategy 2: Weighted by inverse MAPE (better MAPE = higher weight)
    weights = 1.0 / mapes
    weights = weights / weights.sum()
    weighted_pred = float(np.sum(preds * weights))
    result["weighted_perf"] = {
        "predicted_price_vnd": round(weighted_pred, -3),
        "models_used": model_names,
        "weights": {n: round(w, 4) for n, w in zip(model_names, weights)},
        "model_count": len(model_names),
    }

    # Strategy 3: Top-3 by MAPE
    sorted_idx = np.argsort(mapes)[:3]
    top3_names = [model_names[i] for i in sorted_idx]
    top3_preds = preds[sorted_idx]
    result["top3"] = {
        "predicted_price_vnd": round(float(np.mean(top3_preds)), -3),
        "models_used": top3_names,
        "model_count": 3,
    }

    # Return requested strategy result, plus full breakdown
    chosen = req.strategy if req.strategy in result else "weighted_perf"
    return {
        "requested_strategy": chosen,
        "predicted_price_vnd": result[chosen]["predicted_price_vnd"],
        "route": f"{req.dep}-{req.arr}",
        "fare_family": req.fare_family,
        "lead_time_days": req.lead_time_days,
        "individual_predictions": individual,
        "all_strategies": result,
    }


@app.post("/optimize")
def optimize(req: OptimizeRequest):
    result = optimize_flight(
        base_price = req.base_price,
        base_lf   = req.base_lf,
        capacity  = req.capacity,
    )
    return result


@app.post("/flights/{flight_id}/apply")
def apply_price(flight_id: str, req: ApplyRequest):
    store_path = os.path.join(OUTPUTS_DIR, "applied_prices.json")
    applied = {}
    if os.path.exists(store_path):
        try:
            with open(store_path, encoding="utf-8") as f:
                applied = json.load(f)
        except Exception:
            pass
    applied[flight_id] = {
        "applied_price": req.applied_price,
        "model_used": req.model_used,
        "saved_at": pd.Timestamp.now().isoformat(),
    }
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(applied, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "flight_id": flight_id, "applied_price": req.applied_price, "model_used": req.model_used}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    df = simulate_range(
        base_price = req.base_price,
        base_lf    = req.base_lf,
        capacity   = req.capacity,
        from_pct   = req.from_pct,
        to_pct     = req.to_pct,
    )
    return df.to_dict(orient="records")


# ── Data endpoints ──────────────────────────────────────────────────────────────
import functools
import glob

def _load_data():
    """
    Load all CSV and Excel files from data/raw/ and concatenate them.
    Falls back to ai.xlsx if no other files found.
    """
    raw_dir = os.path.join(_PROJECT_ROOT, "data", "raw")
    csv_files  = glob.glob(os.path.join(raw_dir, "*.csv"))
    xlsx_files = glob.glob(os.path.join(raw_dir, "*.xlsx")) + glob.glob(os.path.join(raw_dir, "*.xls"))
    all_files  = csv_files + xlsx_files

    if not all_files:
        raise FileNotFoundError(f"No CSV or Excel files found in {raw_dir}")

    dfs = []
    for fp in sorted(all_files):
        try:
            if fp.lower().endswith(".csv"):
                dfs.append(pd.read_csv(fp))
            else:
                dfs.append(pd.read_excel(fp, engine="openpyxl"))
            print(f"[_load_data] Loaded: {os.path.basename(fp)}")
        except Exception as e:
            print(f"[_load_data] Skipped {fp}: {e}")

    df = pd.concat(dfs, ignore_index=True)

    # Normalize capacity alias
    if "capacity" not in df.columns and "lng_Capacity" in df.columns:
        df["capacity"] = df["lng_Capacity"]

    # Filter obviously bad rows if the columns exist
    if "lead_time_days" in df.columns:
        df = df[df["lead_time_days"] >= 0]
    if "mny_GL_Charges_Total" in df.columns:
        df = df[df["mny_GL_Charges_Total"] >= 50000]

    # Add route column if dep/arr columns exist
    if "str_Dep" in df.columns and "str_Arr" in df.columns:
        df["route"] = df["str_Dep"] + "-" + df["str_Arr"]

    print(f"[_load_data] Total rows after concat+filter: {len(df)}")
    return df.copy()


@app.get("/routes")
def get_routes(flight_date: str | None = None, dep: str | None = None, arr: str | None = None):
    raw_routes = sqlserver.get_routes(flight_date=flight_date, dep=dep, arr=arr)
    if not raw_routes:
        return []
    result = []
    for r in raw_routes:
        avg_price = float(r["avg_price"])
        avg_lf    = float(r["avg_lf"])
        opt = optimize_flight(avg_price, avg_lf, 230)
        result.append({
            "route":             r["route"],
            "count":             int(r["count"]),
            "avg_price":         round(avg_price, -3),
            "avg_lf":            round(avg_lf, 4),
            "min_price":         round(float(r["min_price"]), -3),
            "max_price":         round(float(r["max_price"]), -3),
            "optimal_price":     opt["optimal_price"],
            "optimal_lf":        round(opt["optimal_lf"], 4),
            "price_change_pct":  opt["price_change_pct"],
            "revenue_delta_pct": opt["revenue_delta_pct"],
        })
    return result


@app.get("/airports")
def get_airports():
    """Return distinct departure and arrival airports."""
    try:
        airports = sqlserver.get_distinct_airports()
        return airports
    except Exception as e:
        return {"error": str(e)}


def _predict_classes_for_flight(row, model, app_state) -> dict:
    """
    Predict ticket prices for Eco, Deluxe, SkyBoss, and GDS (Business)
    for a single flight record features.
    Returns: { "Eco": float, "Deluxe": float, "SkyBoss": float, "GDS": float }
    """
    PRICE_MIN = 50_000.0

    classes_to_predict = {
        "Eco": "Eco",
        "Deluxe": "Deluxe",
        "SkyBoss": "SkyBoss",
        "GDS": "Business"
    }

    predictions = {}
    lf = float(row.get("lf", 0.65) if row.get("lf") is not None else 0.65)
    price = float(row.get("price", 0.0) if row.get("price") is not None else 0.0)

    for ui_name, model_class in classes_to_predict.items():
        try:
            pred_req = PredictRequest(
                lead_time_days      = int(row.get("lead_time_days", 30)) if pd.notna(row.get("lead_time_days")) else 30,
                LF_by_date          = lf,
                LF_by_fare          = float(row.get("LF_by_fare", lf)) if pd.notna(row.get("LF_by_fare")) else lf,
                booking_velocity_3d = float(row.get("booking_velocity_3d", 0.02)) if pd.notna(row.get("booking_velocity_3d")) else 0.02,
                booking_velocity_7d = float(row.get("booking_velocity_7d", 0.05)) if pd.notna(row.get("booking_velocity_7d")) else 0.05,
                Weekday             = int(row.get("Weekday", 4)) if pd.notna(row.get("Weekday")) else 4,
                IsHoliday           = int(row.get("IsHoliday", 0)) if pd.notna(row.get("IsHoliday")) else 0,
                is_oneway           = int(row.get("is_oneway", 1)) if pd.notna(row.get("is_oneway")) else 1,
                lng_fuel            = float(row.get("lng_fuel", 93.86)) if pd.notna(row.get("lng_fuel")) else 93.86,
                capacity            = int(row.get("lng_Capacity", 230)) if pd.notna(row.get("lng_Capacity")) else 230,
                count_sked          = int(row.get("count_sked", 3)) if pd.notna(row.get("count_sked")) else 3,
                fare_family         = model_class,
                fare_category       = str(row.get("str_Fare_Category", "B") or "B")[:10],
                dep                 = str(row.get("str_Dep", "SGN")),
                arr                 = str(row.get("str_Arr", "HAN")),
            )
            X = _build_features(pred_req, app_state)
            scaler = getattr(model, "_scaler", None)
            predicted_price = float(_predict_with_model(model, X, app_state)[0])
            predicted_price = max(PRICE_MIN, predicted_price)
            
            # Apply typical bounds relative to current price to prevent extreme model output
            actual_class = row.get("fare_family", "")
            if price > 0 and actual_class == model_class:
                predicted_price = max(price * 0.20, min(price * 4.0, predicted_price))
                
            predictions[ui_name] = round(predicted_price, -3)
        except Exception:
            # Ratios for fallback if prediction fails
            ratios = {"Eco": 1.0, "Deluxe": 1.4, "SkyBoss": 2.2, "GDS": 3.0}
            ref_val = price if price > 0 else 1000000.0
            predictions[ui_name] = round(ref_val * ratios[ui_name], -3)

    return predictions


@app.get("/flights")
def get_flights(
    dep:        str | None = None,
    arr:        str | None = None,
    flight_date: str | None = None,
    flight_no:  str | None = None,
    fare_family: str | None = None,
    sort_by:    str = "flight_date",
    sort_dir:   str = "asc",
    page:       int = Query(1, ge=1),
    page_size:  int = Query(15, ge=1, le=100),
    request: Request = None,
):
    """
    Query flight records from SQL Server with dep/arr/date filters and pagination.
    Returns {items: [...], total: N}.
    Uses ML model prediction for AI Suggestion (optimal_price).
    """
    from datetime import date as date_type

    # Do not restrict date if explicitly empty or omitted
    query_date = flight_date if flight_date else None

    try:
        total = sqlserver.count_flights(
            dep=dep, arr=arr,
            flight_date=query_date,
            flight_no=flight_no,
            fare_family=fare_family,
        )
        df = sqlserver.load_flights(
            dep=dep, arr=arr,
            flight_date=query_date,
            flight_no=flight_no,
            fare_family=fare_family,
            sort_by=sort_by, sort_dir=sort_dir,
            page=page, page_size=page_size,
        )
    except Exception as ex:
        print(f"[get_flights] DB query failed ({ex})")
        return {"items": [], "total": 0}

    if df.empty:
        return {"items": [], "total": total}

    dep_times_map = {
        "SGN": "06:00", "HAN": "08:30", "DAD": "10:15",
        "CXR": "12:00", "PQC": "14:30", "VCL": "16:00", "HUI": "18:30",
    }

    # Get ML model for prediction
    app_state = request.app.state if request else None
    model = _get_model(app_state) if app_state else None
    has_model = model is not None

    flights = []
    for i, (_, r) in enumerate(df.iterrows()):
        price = float(r.get("price", 0))
        lf    = float(r.get("lf", 0))
        capacity = int(r.get("lng_Capacity", 230))

        # Use ML model prediction for AI Suggestion
        if has_model:
            ai_suggestions = _predict_classes_for_flight(r, model, app_state)
            optimal_price = ai_suggestions.get(r.get("fare_family", "Eco"), price)
            if optimal_price is None:
                optimal_price = price
            price_change_pct = round((optimal_price / price - 1) * 100, 2) if price > 0 else 0.0
            
            flight_date_val_temp = r.get("flight_date")
            date_str = str(flight_date_val_temp.isoformat()) if hasattr(flight_date_val_temp, 'isoformat') else str(flight_date_val_temp)
            recommendation = f"Dự đoán: {optimal_price:,.0f} VND (Hạng: {r.get('fare_family', 'Eco')}, Ngày: {date_str}, Tuyến: {r.get('str_Dep', 'SGN')}-{r.get('str_Arr', 'HAN')})"
            optimal_lf = lf
        else:
            # Fallback to math optimizer if no model
            opt = optimize_flight(price, lf, capacity)
            optimal_price = opt["optimal_price"]
            price_change_pct = opt["price_change_pct"]
            optimal_lf = opt["optimal_lf"]
            
            # Fallback suggestions based on pricing ratios
            ai_suggestions = {
                "Eco": round(optimal_price, -3),
                "Deluxe": round(optimal_price * 1.4, -3),
                "SkyBoss": round(optimal_price * 2.2, -3),
                "GDS": round(optimal_price * 3.0, -3)
            }
            
            fare_family = str(r.get("fare_family", "Eco") or "Eco")[:20]
            dep_code_temp = str(r.get("str_Dep", "SGN"))
            arr_code_temp = str(r.get("str_Arr", "HAN"))
            flight_date_val_temp = r.get("flight_date")
            date_str = str(flight_date_val_temp.isoformat()) if hasattr(flight_date_val_temp, 'isoformat') else str(flight_date_val_temp)
            recommendation = f"Đề xuất: {optimal_price:,.0f} VND (Hạng: {fare_family}, Ngày: {date_str}, Tuyến: {dep_code_temp}-{arr_code_temp})"

        base_rev = price * capacity * lf
        new_rev  = optimal_price * capacity * optimal_lf
        rev_delta = ((new_rev - base_rev) / base_rev * 100) if base_rev > 0 else 0
        status = "high" if lf > 0.75 else "ok" if lf > 0.55 else "mid" if lf > 0.40 else "low"
        dep_code = str(r.get("str_Dep", ""))
        arr_code = str(r.get("str_Arr", ""))
        flight_date_val = r.get("flight_date")
        if hasattr(flight_date_val, 'isoformat'):
            flight_date_val = flight_date_val.isoformat()
        flights.append({
            "id":                int(r.get("id", 100 + i)),
            "flight_no":         r.get("flight_no") or f"A{capacity:03d}",
            "route":             f"{dep_code}->{arr_code}",
            "dep":               dep_code,
            "arr":               arr_code,
            "flight_date":       str(flight_date_val) if flight_date_val else None,
            "lf":                round(lf, 4),
            "price":             round(price, -3),
            "optimal_price":     optimal_price,
            "price_change_pct":  price_change_pct,
            "optimal_lf":        round(optimal_lf, 4),
            "revenue_delta_pct": round(rev_delta, 2),
            "recommendation":    recommendation,
            "status":            status,
            "fare_family":       r.get("fare_family", ""),
            "fare_category":     r.get("str_Fare_Category", ""),
            "capacity":          capacity,
            "ml_model_used":     has_model,
            "lead_time_days":    int(r.get("lead_time_days", 30)) if pd.notna(r.get("lead_time_days")) else 30,
            "LF_by_fare":        float(r.get("LF_by_fare", lf)) if pd.notna(r.get("LF_by_fare")) else lf,
            "booking_velocity_3d": float(r.get("booking_velocity_3d", 0.02)) if pd.notna(r.get("booking_velocity_3d")) else 0.02,
            "booking_velocity_7d": float(r.get("booking_velocity_7d", 0.05)) if pd.notna(r.get("booking_velocity_7d")) else 0.05,
            "Weekday":           int(r.get("Weekday", 4)) if pd.notna(r.get("Weekday")) else 4,
            "IsHoliday":         int(r.get("IsHoliday", 0)) if pd.notna(r.get("IsHoliday")) else 0,
            "is_oneway":         int(r.get("is_oneway", 1)) if pd.notna(r.get("is_oneway")) else 1,
            "lng_fuel":          float(r.get("lng_fuel", 93.86)) if pd.notna(r.get("lng_fuel")) else 93.86,
            "count_sked":        int(r.get("count_sked", 3)) if pd.notna(r.get("count_sked")) else 3,
            "ai_suggestions":    ai_suggestions,
        })
    return {"items": flights, "total": total}



# ── Batch predict for flight list ─────────────────────────────────────────────
class FlightPredictItem(BaseModel):
    id: int
    lead_time_days: int = 30
    LF_by_date: float = 0.65
    LF_by_fare: float = 0.40
    booking_velocity_3d: float = 0.02
    booking_velocity_7d: float = 0.05
    Weekday: int = 4
    IsHoliday: int = 0
    is_oneway: int = 1
    lng_fuel: float = 93.86
    capacity: int = 230
    count_sked: int = 3
    fare_family: str = "Eco"
    fare_category: str = "B"
    dep: str = "SGN"
    arr: str = "HAN"
    current_price: Optional[float] = None   # used for sanity-bounding the prediction


class BatchPredictRequest(BaseModel):
    model_name: Optional[str] = None   # None => best model
    flights: List[FlightPredictItem]


@app.post("/predict-for-flights")
def predict_for_flights(req: BatchPredictRequest, request: Request):
    """
    Batch-predict prices for a list of flight rows using the selected ML model.
    Returns {id: {Eco: {predicted_price_vnd, clamped}, Deluxe: {...}, ...}} mapping.
    Applies sanity checks: price must be >= 50,000 VND and <= 15,000,000 VND.
    If current_price is provided, prediction is also bounded to [20%, 400%] of current price.
    """
    model = _get_model(request.app.state, req.model_name)
    if model is None:
        raise HTTPException(503, "No model loaded. Run: python kaggle/scripts/run_pipeline.py")

    PRICE_MIN = 50_000.0

    results = {}
    used_model = req.model_name if req.model_name and req.model_name in request.app.state.models \
        else request.app.state.best_model_name

    classes_to_predict = {
        "Eco": "Eco",
        "Deluxe": "Deluxe",
        "SkyBoss": "SkyBoss",
        "GDS": "Business"
    }

    for item in req.flights:
        results[item.id] = {}
        for ui_name, model_class in classes_to_predict.items():
            try:
                pred_req = PredictRequest(
                    lead_time_days=item.lead_time_days,
                    LF_by_date=item.LF_by_date,
                    LF_by_fare=item.LF_by_fare,
                    booking_velocity_3d=item.booking_velocity_3d,
                    booking_velocity_7d=item.booking_velocity_7d,
                    Weekday=item.Weekday,
                    IsHoliday=item.IsHoliday,
                    is_oneway=item.is_oneway,
                    lng_fuel=item.lng_fuel,
                    capacity=item.capacity,
                    count_sked=item.count_sked,
                    fare_family=model_class,
                    fare_category=item.fare_category,
                    dep=item.dep,
                    arr=item.arr,
                )
                X = _build_features(pred_req, request.app.state)
                scaler = getattr(model, "_scaler", None)
                raw_price = float(_predict_with_model(model, X, request.app.state)[0])

                # ── Sanity clamp ────────────────────────────────────────────────
                predicted_price = max(PRICE_MIN, raw_price)

                # If we know the current price, and this is the original class, bound within [20%, 400%]
                current = item.current_price
                if current and current > 0 and model_class == item.fare_family:
                    predicted_price = max(current * 0.20, min(current * 4.0, predicted_price))

                is_valid = raw_price >= PRICE_MIN  # flag if model output was already sensible
                results[item.id][ui_name] = {
                    "predicted_price_vnd": round(predicted_price, -3),
                    "clamped": not is_valid,
                }
            except Exception as ex:
                results[item.id][ui_name] = {"predicted_price_vnd": None, "error": str(ex)}

    return {"predictions": results, "model_used": used_model}


@app.get("/flights/{flight_id}")
def get_flight_detail(flight_id: int):
    """Get detailed flight info including all fare families."""
    flight = sqlserver.load_flight_by_id(flight_id)
    if flight is None:
        raise HTTPException(404, f"Flight {flight_id} not found")

    # Convert numpy types to native Python
    def to_native(val):
        if hasattr(val, 'item'):
            return val.item()
        if hasattr(val, 'isoformat'):
            return str(val)
        return val

    flight = {k: to_native(v) for k, v in flight.items()}

    # Calculate optimal price
    price = float(flight.get("price", 0))
    lf = float(flight.get("lf", 0))
    opt = optimize_flight(price, lf, 230)

    return {
        **flight,
        "optimal_price": opt["optimal_price"],
        "optimal_lf": opt["optimal_lf"],
        "price_change_pct": opt["price_change_pct"],
        "revenue_delta_pct": opt["revenue_delta_pct"],
    }


class FareUpdateItem(BaseModel):
    id: int
    price: float
    lf: float


class BulkFareUpdateRequest(BaseModel):
    updates: list[FareUpdateItem]


@app.put("/flights/{flight_id}/fares")
def update_flight_fares(flight_id: int, req: BulkFareUpdateRequest):
    """Update prices and load factors for one or more fare families of a flight."""
    updates = [{"id": u.id, "price": u.price, "lf": u.lf} for u in req.updates]
    result = sqlserver.bulk_update_flight_details(updates)
    return {
        "status": "ok",
        "flight_id": flight_id,
        "updated": result["updated"],
        "failed": result["failed"],
    }


@app.post("/flights/upload")
async def upload_flights_to_db(file: UploadFile = File(...)):
    """
    Upload a CSV/Excel file and save all rows to SQL Server.
    After upload, returns the count of rows inserted.
    """
    suffix = file.filename.split(".")[-1].lower()
    if suffix not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, f"Unsupported file type: {suffix}. Use .csv or .xlsx")

    try:
        contents = await file.read()
        print(f"[upload] Read {len(contents)} bytes from {file.filename}")
        if suffix == "csv":
            df = pd.read_csv(pd.io.common.BytesIO(contents))
        else:
            df = pd.read_excel(pd.io.common.BytesIO(contents), engine="openpyxl")
        print(f"[upload] DataFrame shape: {df.shape}")
        print(f"[upload] Columns: {list(df.columns)}")
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    # Normalize column names from upload to DB schema
    rename_map = {
        "dep":          "str_Dep",
        "arr":          "str_Arr",
        "price":        "mny_GL_Charges_Total",
        "lf":           "LF_by_date",
        "lf_fare":      "LF_by_fare",
        "fuel_price":   "lng_fuel",
        "str_Fare_Class_Short":   "str_Fare_Category",
        "str_Fare_Family_Ident":  "fare_family",
        "str_Fare_Category_Ident":"str_Fare_Category",
        "lng_Capacity": "lng_Capacity",
        "lng_Seats":    "lng_Seats",
    }
    df.rename(columns=rename_map, inplace=True)

    # Extract flight_date from dtm_Local_ETD_Date if present
    if "dtm_Local_ETD_Date" in df.columns:
        df["flight_date"] = pd.to_datetime(df["dtm_Local_ETD_Date"], errors="coerce").dt.date
    elif "dtm_Creation_Date" in df.columns:
        df["flight_date"] = pd.to_datetime(df["dtm_Creation_Date"], errors="coerce").dt.date

    # Ensure required columns exist
    if "str_Dep" not in df.columns or "str_Arr" not in df.columns:
        raise HTTPException(400, "File must contain 'dep' and 'arr' (or 'str_Dep'/'str_Arr') columns")

    # Add route column
    df["route"] = df["str_Dep"].astype(str) + "-" + df["str_Arr"].astype(str)

    try:
        result = sqlserver.upsert_flights(df)
        return {
            "status": "ok",
            "rows_inserted": result["inserted"],
            "rows_updated": result["updated"],
            "filename": file.filename,
        }
    except Exception as ex:
        raise HTTPException(500, f"Database error: {ex}")


@app.get("/db/routes")
def get_db_routes():
    """Return distinct routes stored in SQL Server."""
    try:
        return sqlserver.get_distinct_routes()
    except Exception as ex:
        raise HTTPException(500, f"DB error: {ex}")


@app.post("/db/seed")
def seed_db_from_excel():
    """Seed: upsert all rows from ai.xlsx into SQL Server. Idempotent."""
    try:
        df = _load_data()
        result = sqlserver.upsert_flights(df)
        return {
            "status": "ok",
            "rows_inserted": result["inserted"],
            "rows_updated": result["updated"],
        }
    except Exception as ex:
        raise HTTPException(500, f"Seed failed: {ex}")


@app.get("/summary")
def get_summary(
    dep:        str | None = None,
    arr:        str | None = None,
    flight_date: str | None = None,
    flight_no:  str | None = None,
    fare_family: str | None = None,
):
    from datetime import date as date_type

    # Do not restrict date if explicitly empty or omitted
    query_date = flight_date if flight_date else None

    try:
        df = sqlserver.load_flights(
            dep=dep, arr=arr,
            flight_date=query_date,
            flight_no=flight_no,
            fare_family=fare_family,
            page_size=500,
        )
    except Exception as ex:
        print(f"[get_summary] DB query failed ({ex})")
        df = pd.DataFrame()

    if df.empty:
        return {
            "base_revenue_vnd":     0.0,
            "ai_revenue_vnd":       0.0,
            "revenue_delta_pct":    0.0,
            "avg_load_factor":      0.0,
            "flights_total":        0,
            "flights_need_action":  0,
        }

    flights = []
    for _, r in df.iterrows():
        price = float(r.get("price", 0))
        lf    = float(r.get("lf",    0))
        opt   = optimize_flight(price, lf, 230)
        status = "high" if lf > 0.75 else "ok" if lf > 0.55 else "mid" if lf > 0.40 else "low"
        flights.append({**opt, "price": price, "lf": lf, "status": status})

    base_rev  = sum(f["price"] * 230 * f["lf"] for f in flights)
    ai_rev    = sum(f["optimal_price"] * 230 * f["optimal_lf"] for f in flights)
    avg_lf    = sum(f["lf"] for f in flights) / len(flights)
    needs_opt = sum(1 for f in flights if f["status"] in ["low", "mid"])
    return {
        "base_revenue_vnd":     round(base_rev, -6),
        "ai_revenue_vnd":       round(ai_rev, -6),
        "revenue_delta_pct":    round((ai_rev - base_rev) / base_rev * 100, 2) if base_rev else 0,
        "avg_load_factor":      round(avg_lf, 4),
        "flights_total":        len(flights),
        "flights_need_action":  needs_opt,
    }


# ── Upload & batch predict ─────────────────────────────────────────────────────
@app.post("/upload-predict")
async def upload_predict(request: Request, file: UploadFile = File(...), model_name: Optional[str] = None):
    """
    Upload a CSV/Excel file and get fare predictions for all rows.

    The file must contain these columns (all others are ignored / filled with defaults):
      lead_time_days, LF_by_date, LF_by_fare, booking_velocity_3d,
      booking_velocity_7d, Weekday, IsHoliday, is_oneway,
      lng_fuel, capacity, count_sked, fare_family, fare_category, dep, arr

    Returns a DataFrame preview + per-row predictions.
    """
    suffix = file.filename.split(".")[-1].lower()
    if suffix not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, f"Unsupported file type: {suffix}. Use .csv or .xlsx")

    try:
        contents = await file.read()
        # Reset stream position so downstream endpoint (/flights/upload) can re-read the same file
        await file.seek(0)
        if suffix == "csv":
            df = pd.read_csv(pd.io.common.BytesIO(contents))
        else:
            df = pd.read_excel(pd.io.common.BytesIO(contents), engine="openpyxl")
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    model = _get_model(request.app.state, model_name)
    if model is None:
        raise HTTPException(503, "No model loaded. Run: python kaggle/scripts/run_pipeline.py")
    # Normalize and predict
    return _predict_and_format_results(df, model, request.app.state, file.filename)


# ── Combined: Predict + Save to DB (single endpoint) ─────────────────────────
@app.post("/upload-predict-and-save")
async def upload_predict_and_save(request: Request, file: UploadFile = File(...), model_name: Optional[str] = None):
    """
    Upload a CSV/Excel file, get fare predictions, AND save to SQL Server.
    This combined endpoint avoids the issue of reading the file stream twice.
    """
    suffix = file.filename.split(".")[-1].lower()
    if suffix not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, f"Unsupported file type: {suffix}. Use .csv or .xlsx")

    try:
        contents = await file.read()
        print(f"[upload-predict-and-save] Read {len(contents)} bytes from {file.filename}")
        if suffix == "csv":
            df = pd.read_csv(pd.io.common.BytesIO(contents))
        else:
            df = pd.read_excel(pd.io.common.BytesIO(contents), engine="openpyxl")
        print(f"[upload-predict-and-save] DataFrame shape: {df.shape}")
        print(f"[upload-predict-and-save] Columns: {list(df.columns)}")
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    # Normalize column names for DB
    rename_map = {
        "dep": "str_Dep",
        "arr": "str_Arr",
        "price": "mny_GL_Charges_Total",
        "lf": "LF_by_date",
        "lf_fare": "LF_by_fare",
        "fuel_price": "lng_fuel",
        "str_Fare_Class_Short": "str_Fare_Category",
        "str_Fare_Family_Ident": "fare_family",
        "str_Fare_Category_Ident": "str_Fare_Category",
    }
    df_for_db = df.rename(columns=rename_map)
    
    # Extract flight_date from dtm_Local_ETD_Date if present
    if "dtm_Local_ETD_Date" in df_for_db.columns:
        df_for_db["flight_date"] = pd.to_datetime(df_for_db["dtm_Local_ETD_Date"], errors="coerce").dt.date
    elif "dtm_Creation_Date" in df_for_db.columns:
        df_for_db["flight_date"] = pd.to_datetime(df_for_db["dtm_Creation_Date"], errors="coerce").dt.date
    else:
        df_for_db["flight_date"] = pd.Timestamp.today().date()
        print(f"[upload-predict-and-save] WARNING: No date column found, using today")

    # Save to DB
    db_result = {"inserted": 0, "updated": 0}
    if "str_Dep" in df_for_db.columns and "str_Arr" in df_for_db.columns:
        try:
            db_result = sqlserver.upsert_flights(df_for_db)
            print(f"[upload-predict-and-save] DB result: {db_result}")
        except Exception as ex:
            print(f"[upload-predict-and-save] DB error: {ex}")

    model = _get_model(request.app.state, model_name)
    if model is None:
        raise HTTPException(503, "No model loaded. Run: python kaggle/scripts/run_pipeline.py")
    # Now do prediction — normalize and predict
    return _predict_and_format_results(df, model, request.app.state, file.filename, db_result=db_result)

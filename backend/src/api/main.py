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
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
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
    except Exception as ex:
        print(f"[startup] DB init warning: {ex}")

    enc_path = os.path.join(OUTPUTS_DIR, "label_encoders.pkl")
    if os.path.exists(enc_path):
        app.state.label_encoders = joblib.load(enc_path)
        print(f"Encoders loaded: {enc_path}")
    else:
        app.state.label_encoders = {}
        print("Warning: Label encoders not found")

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


# ── Helpers ─────────────────────────────────────────────────────────────────────
def _build_features(req: PredictRequest, app_state) -> pd.DataFrame:
    route = f"{req.dep}-{req.arr}"

    urgency_score        = req.LF_by_date / (req.lead_time_days + 1)
    velocity_ratio       = req.booking_velocity_3d / (req.booking_velocity_7d + 1e-6)
    seats_remaining      = int(req.capacity * (1 - req.LF_by_date))
    is_weekend          = int(req.Weekday in [5, 6])
    days_bucket         = min(6, max(0, int(req.lead_time_days // 10)))
    fare_fill_rate      = req.LF_by_fare
    log_lead_time       = np.log1p(req.lead_time_days)
    lf_velocity_interact = req.LF_by_date * req.booking_velocity_7d
    expected_sold        = int(req.capacity * req.LF_by_date)

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
        "fare_fill_rate":        fare_fill_rate,
        "log_lead_time":         log_lead_time,
        "lf_velocity_interact":   lf_velocity_interact,
        "expected_sold":         expected_sold,
    }

    label_encoders = getattr(app_state, "label_encoders", {}) or {}
    feature_names = getattr(app_state, "feature_names", []) or []

    for col, enc_col, val in [
        ("fare_family",  "fare_family_enc",  req.fare_family),
        ("fare_category","fare_category_enc", req.fare_category),
        ("route",        "route_enc",        route),
    ]:
        le = label_encoders.get(col)
        if le:
            row[enc_col] = int(le.transform([val])[0]) if val in le.classes_ else -1

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
    predicted_price = float(model.predict(X)[0])

    return {
        "predicted_price_vnd": round(predicted_price, -3),
        "route": f"{req.dep}-{req.arr}",
        "fare_family": req.fare_family,
        "lead_time_days": req.lead_time_days,
        "model_used": used_model,
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
    individual = {}
    for name, model in models.items():
        try:
            scaler = getattr(model, "_scaler", None)
            X_run = scaler.transform(X) if scaler else X
            pred = float(model.predict(X_run)[0])
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
        "saved_at": pd.Timestamp.now().isoformat(),
    }
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(applied, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "flight_id": flight_id, "applied_price": req.applied_price}


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
def get_routes():
    raw_routes = sqlserver.get_routes()
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
            "price_change_pct":  opt["price_change_pct"],
            "revenue_delta_pct": opt["revenue_delta_pct"],
        })
    return result


@app.get("/flights")
def get_flights(
    dep:        str | None = None,
    arr:        str | None = None,
    flight_date: str | None = None,
    sort_by:    str = "flight_date",
    sort_dir:   str = "asc",
    page:       int = 1,
    page_size:  int = 15,
):
    """
    Query flight records from SQL Server with dep/arr/date filters and pagination.
    Returns {items: [...], total: N}.
    """
    from datetime import date as date_type

    today = date_type.today().isoformat()
    # If no filters at all, default to today or recent
    use_today_fallback = not dep and not arr and not flight_date

    try:
        if use_today_fallback:
            # Count with today filter
            total = sqlserver.count_flights(flight_date=today)
            if total == 0:
                # Fallback: all recent flights
                total = sqlserver.count_flights()
                df = sqlserver.load_flights(
                    sort_by=sort_by, sort_dir=sort_dir,
                    page=page, page_size=page_size,
                )
            else:
                df = sqlserver.load_flights(
                    flight_date=today,
                    sort_by=sort_by, sort_dir=sort_dir,
                    page=page, page_size=page_size,
                )
        else:
            total = sqlserver.count_flights(
                dep=dep, arr=arr,
                flight_date=flight_date,
            )
            df = sqlserver.load_flights(
                dep=dep, arr=arr,
                flight_date=flight_date,
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
    flights = []
    for i, (_, r) in enumerate(df.iterrows()):
        price = float(r.get("price", 0))
        lf    = float(r.get("lf", 0))
        opt   = optimize_flight(price, lf, 230)
        base_rev = price * 230 * lf
        new_rev  = opt["optimal_price"] * 230 * opt["optimal_lf"]
        rev_delta = ((new_rev - base_rev) / base_rev * 100) if base_rev > 0 else 0
        status = "high" if lf > 0.75 else "ok" if lf > 0.55 else "mid" if lf > 0.40 else "low"
        dep_code = str(r.get("str_Dep", ""))
        arr_code = str(r.get("str_Arr", ""))
        flight_date_val = r.get("flight_date")
        if hasattr(flight_date_val, 'isoformat'):
            flight_date_val = flight_date_val.isoformat()
        flights.append({
            "id":                int(r.get("id", 100 + i)),
            "flight_no":         r.get("flight_no") or f"VJ{100 + i}",
            "route":             f"{dep_code}->{arr_code}",
            "dep":               dep_times_map.get(dep_code, dep_times_map.get(arr_code, "08:00")),
            "flight_date":       str(flight_date_val) if flight_date_val else None,
            "lf":                round(lf, 4),
            "price":             round(price, -3),
            "optimal_price":     opt["optimal_price"],
            "price_change_pct":  opt["price_change_pct"],
            "optimal_lf":        opt["optimal_lf"],
            "revenue_delta_pct": round(rev_delta, 2),
            "recommendation":    opt["recommendation"],
            "status":            status,
            "fare_family":       r.get("fare_family", ""),
            "fare_category":     r.get("str_Fare_Category", ""),
            "capacity":          int(r.get("lng_Capacity", 230)),
        })
    return {"items": flights, "total": total}


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


class BulkFareUpdateRequest(BaseModel):
    updates: list[FareUpdateItem]


@app.put("/flights/{flight_id}/fares")
def update_flight_fares(flight_id: int, req: BulkFareUpdateRequest):
    """Update prices for one or more fare families of a flight."""
    updates = [{"id": u.id, "price": u.price} for u in req.updates]
    result = sqlserver.bulk_update_flight_prices(updates)
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
):
    from datetime import date as date_type

    today = date_type.today().isoformat()
    # If no filters at all, or if the filter is just today's date but there are no flights today:
    use_today_fallback = (not dep and not arr and not flight_date) or (flight_date == today and not dep and not arr)

    try:
        if use_today_fallback:
            total_today = sqlserver.count_flights(flight_date=today)
            if total_today == 0:
                df = sqlserver.load_flights(page_size=500)
            else:
                df = sqlserver.load_flights(flight_date=today, page_size=500)
        else:
            df = sqlserver.load_flights(
                dep=dep, arr=arr,
                flight_date=flight_date,
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

    # Normalize capacity: accept both 'capacity' and 'lng_Capacity'
    if "capacity" not in df.columns and "lng_Capacity" in df.columns:
        df = df.copy()
        df["capacity"] = df["lng_Capacity"]
    # Normalize fare_family: accept str_Fare_Family_Ident
    if "fare_family" not in df.columns and "str_Fare_Family_Ident" in df.columns:
        df = df.copy()
        df["fare_family"] = df["str_Fare_Family_Ident"]
    # Normalize fare_category: accept str_Fare_Category_Ident
    if "fare_category" not in df.columns and "str_Fare_Category_Ident" in df.columns:
        df = df.copy()
        df["fare_category"] = df["str_Fare_Category_Ident"]
    # Normalize dep/arr from str_Dep / str_Arr
    if "dep" not in df.columns and "str_Dep" in df.columns:
        df = df.copy()
        df["dep"] = df["str_Dep"]
    if "arr" not in df.columns and "str_Arr" in df.columns:
        df = df.copy()
        df["arr"] = df["str_Arr"]

    required_cols = ["lead_time_days", "LF_by_date", "LF_by_fare",
                     "booking_velocity_3d", "booking_velocity_7d",
                     "Weekday", "IsHoliday", "is_oneway",
                     "lng_fuel", "capacity", "count_sked"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Missing required columns: {missing}")

    model = _get_model(request.app.state, model_name)

    # Build feature matrix
    X = pd.DataFrame()
    for col in required_cols:
        X[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Encode categorical fields
    categorical_mappings = {
        "fare_family": ["Eco", "Eco-Premium", "SkyBoss", "Business"],
        "fare_category": ["Y", "M", "B", "H", "K", "V", "S", "L", "Q", "N", "O"],
    }
    for cat_field, categories in categorical_mappings.items():
        if cat_field in df.columns:
            raw = df[cat_field].astype(str).str.strip().str[:10]
        else:
            raw = pd.Series(["Eco"] * len(df))
        for cat in categories:
            X[f"{cat_field}_{cat}"] = (raw == cat).astype(int)
        X.drop(f"{cat_field}", axis=1, errors="ignore", inplace=True)

    # Encode dep/arr if present
    label_encoders = getattr(request.app.state, "label_encoders", {}) or {}
    if "dep" in df.columns and "arr" in df.columns and label_encoders:
        dep_enc = label_encoders.get("dep") if hasattr(label_encoders, "get") else label_encoders
        arr_enc = label_encoders.get("arr") if hasattr(label_encoders, "get") else label_encoders
        if dep_enc:
            X["route_enc"] = dep_enc.transform(df["dep"].astype(str).str.strip().str[:3])
        if arr_enc:
            X["route_arr_enc"] = arr_enc.transform(df["arr"].astype(str).str.strip().str[:3])

    # Engineered features
    X["urgency_score"]    = (1 - X["LF_by_date"]) * np.exp(-X["lead_time_days"] / 30)
    X["velocity_ratio"]   = X["booking_velocity_7d"] / (X["booking_velocity_3d"] + 1e-6)
    X["seats_remaining"]  = (X["capacity"] * (1 - X["LF_by_date"])).clip(lower=0)
    X["is_weekend"]       = (X["Weekday"] >= 5).astype(int)
    X["days_bucket"]       = pd.cut(X["lead_time_days"], bins=[0, 3, 7, 14, 30, 90, 365],
                                    labels=[0, 1, 2, 3, 4, 5]).astype(float).fillna(3)
    X["log_lead_time"]    = np.log1p(X["lead_time_days"])
    X["lf_velocity_interact"] = X["LF_by_fare"] * X["booking_velocity_7d"]
    X["expected_sold"]     = X["capacity"] * X["LF_by_date"]

    feature_names = getattr(request.app.state, "feature_names", []) or []
    # Align to feature names
    if feature_names:
        for col in feature_names:
            if col not in X.columns:
                X[col] = 0
        X = X[feature_names]
    else:
        for c in (getattr(model, "feature_names_in_", None) or []):
            if c not in X.columns:
                X[c] = 0
        if getattr(model, "feature_names_in_", None):
            X = X[model.feature_names_in_]

    preds = model.predict(X)
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

    # Return JSON-serialisable dict
    return {
        "model_used": model.__class__.__name__,
        "rows_total":  len(df_result),
        "preview": preview_rows,
        "summary": {
            "mean_predicted":   _safe_float(np.round(np.mean(preds), -3)),
            "median_predicted": _safe_float(np.round(np.median(preds), -3)),
            "min_predicted":    _safe_float(np.round(np.min(preds), -3)),
            "max_predicted":    _safe_float(np.round(np.max(preds), -3)),
        },
        "filename": file.filename,
        "rows_inserted": 0,
        "rows_updated": 0,
    }


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

    # Now do prediction — normalize column aliases first
    if "capacity" not in df.columns and "lng_Capacity" in df.columns:
        df = df.copy()
        df["capacity"] = df["lng_Capacity"]
    if "fare_family" not in df.columns and "str_Fare_Family_Ident" in df.columns:
        df = df.copy()
        df["fare_family"] = df["str_Fare_Family_Ident"]
    if "fare_category" not in df.columns and "str_Fare_Category_Ident" in df.columns:
        df = df.copy()
        df["fare_category"] = df["str_Fare_Category_Ident"]
    if "dep" not in df.columns and "str_Dep" in df.columns:
        df = df.copy()
        df["dep"] = df["str_Dep"]
    if "arr" not in df.columns and "str_Arr" in df.columns:
        df = df.copy()
        df["arr"] = df["str_Arr"]

    required_cols = ["lead_time_days", "LF_by_date", "LF_by_fare",
                     "booking_velocity_3d", "booking_velocity_7d",
                     "Weekday", "IsHoliday", "is_oneway",
                     "lng_fuel", "capacity", "count_sked"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Missing required columns: {missing}")

    model = _get_model(request.app.state, model_name)

    X = pd.DataFrame()
    for col in required_cols:
        X[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    categorical_mappings = {
        "fare_family": ["Eco", "Eco-Premium", "SkyBoss", "Business"],
        "fare_category": ["Y", "M", "B", "H", "K", "V", "S", "L", "Q", "N", "O"],
    }
    for cat_field, categories in categorical_mappings.items():
        if cat_field in df.columns:
            raw = df[cat_field].astype(str).str.strip().str[:10]
        else:
            raw = pd.Series(["Eco"] * len(df))
        for cat in categories:
            X[f"{cat_field}_{cat}"] = (raw == cat).astype(int)
        X.drop(f"{cat_field}", axis=1, errors="ignore", inplace=True)

    label_encoders = getattr(request.app.state, "label_encoders", {}) or {}
    if "dep" in df.columns and "arr" in df.columns and label_encoders:
        dep_enc = label_encoders.get("dep") if hasattr(label_encoders, "get") else label_encoders
        arr_enc = label_encoders.get("arr") if hasattr(label_encoders, "get") else label_encoders
        if dep_enc:
            X["route_enc"] = dep_enc.transform(df["dep"].astype(str).str.strip().str[:3])
        if arr_enc:
            X["route_arr_enc"] = arr_enc.transform(df["arr"].astype(str).str.strip().str[:3])

    X["urgency_score"]    = (1 - X["LF_by_date"]) * np.exp(-X["lead_time_days"] / 30)
    X["velocity_ratio"]   = X["booking_velocity_7d"] / (X["booking_velocity_3d"] + 1e-6)
    X["seats_remaining"]  = (X["capacity"] * (1 - X["LF_by_date"])).clip(lower=0)
    X["is_weekend"]       = (X["Weekday"] >= 5).astype(int)
    X["days_bucket"]       = pd.cut(X["lead_time_days"], bins=[0, 3, 7, 14, 30, 90, 365],
                                    labels=[0, 1, 2, 3, 4, 5]).astype(float).fillna(3)
    X["log_lead_time"]    = np.log1p(X["lead_time_days"])
    X["lf_velocity_interact"] = X["LF_by_fare"] * X["booking_velocity_7d"]
    X["expected_sold"]     = X["capacity"] * X["LF_by_date"]

    feature_names = getattr(request.app.state, "feature_names", []) or []
    if feature_names:
        for col in feature_names:
            if col not in X.columns:
                X[col] = 0
        X = X[feature_names]
    else:
        for c in (getattr(model, "feature_names_in_", None) or []):
            if c not in X.columns:
                X[c] = 0
        if getattr(model, "feature_names_in_", None):
            X = X[model.feature_names_in_]

    preds = model.predict(X)
    df_result = df.copy()
    df_result["predicted_fare_vnd"] = np.round(preds, -3).astype(int)
    if "mny_GL_Charges_Total" in df_result.columns:
        df_result["actual_fare_vnd"] = df_result["mny_GL_Charges_Total"]

    def _safe_float(v):
        """Convert to float, replacing NaN/Inf with None for JSON safety."""
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
            elif hasattr(v, 'item'):  # numpy scalar
                out[k] = _safe_float(v.item())
            else:
                out[k] = v
        return out

    preview_rows = [_sanitize_row(r) for r in df_result.head(20).to_dict(orient="records")]

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
        "filename": file.filename,
        "rows_inserted": db_result["inserted"],
        "rows_updated": db_result["updated"],
    }

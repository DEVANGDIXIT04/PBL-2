"""Anomaly-aware spending forecasts.

Flagged expenses are replaced with the category median before fitting so one
spike cannot drag the next-period forecast. The original series is kept for
the chart. Prediction intervals are residual-based: point ± 1.96 residual std.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", module="statsmodels")


@dataclass
class FitResult:
    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    model_name: str


def fit_and_forecast(values: np.ndarray, horizon: int, granularity: str = "monthly") -> FitResult:
    """Forecast `horizon` steps from a one-dimensional spending series."""
    series = np.asarray(values, dtype=float)
    series = series[np.isfinite(series)]
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if len(series) == 0:
        zeros = np.zeros(horizon, dtype=float)
        return FitResult(zeros, zeros, zeros, "empty")

    model_name = _model_name(len(series), granularity)
    point, fitted, model_name = _fit(series, horizon, granularity, model_name)
    residual = series - fitted[: len(series)]
    sigma = float(np.nanstd(residual))
    if not np.isfinite(sigma) or sigma < 1e-6:
        sigma = float(np.nanstd(series) or 1.0)
    lower = np.clip(point - 1.96 * sigma, 0, None)
    upper = np.clip(point + 1.96 * sigma, 0, None)
    point = np.clip(point, 0, None)
    return FitResult(point=point, lower=lower, upper=upper, model_name=model_name)


def _model_name(length: int, granularity: str) -> str:
    if granularity == "monthly" and length >= 24:
        return "holt_winters"
    if granularity == "weekly" and length >= 104:
        return "holt_winters"
    if length >= 8:
        return "holt"
    if length >= 3:
        return "ses"
    return "moving_average"


def _fit(
    series: np.ndarray, horizon: int, granularity: str, model_name: str
) -> tuple[np.ndarray, np.ndarray, str]:
    if model_name == "moving_average":
        return _moving_average(series, horizon), series.copy(), "moving_average"
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        seasonal = None
        periods = None
        trend = None
        if model_name == "holt_winters":
            trend = "add"
            seasonal = "add"
            periods = 12 if granularity == "monthly" else 52
        elif model_name == "holt":
            trend = "add"
        model = ExponentialSmoothing(
            series,
            trend=trend,
            seasonal=seasonal,
            seasonal_periods=periods,
            initialization_method="estimated",
        )
        fit_kwargs: dict[str, float | bool] = {"smoothing_level": 0.4, "optimized": False}
        if trend is not None:
            fit_kwargs["smoothing_trend"] = 0.2
        if seasonal is not None:
            fit_kwargs["smoothing_seasonal"] = 0.2
        fitted_model = model.fit(**fit_kwargs)
        point = np.asarray(fitted_model.forecast(horizon), dtype=float)
        fitted = np.asarray(fitted_model.fittedvalues, dtype=float)
        if not np.isfinite(point).all():
            raise ValueError("non-finite forecast")
        return point, fitted, model_name
    except Exception:
        return _moving_average(series, horizon), _rolling_fitted(series), "moving_average"


def _moving_average(series: np.ndarray, horizon: int) -> np.ndarray:
    window = min(3, len(series))
    level = float(np.mean(series[-window:]))
    return np.repeat(level, horizon)


def _rolling_fitted(series: np.ndarray) -> np.ndarray:
    fitted = np.zeros_like(series)
    for index in range(len(series)):
        start = max(0, index - 3)
        window = series[start:index]
        fitted[index] = float(np.mean(window)) if len(window) else float(series[index])
    return fitted


def replace_anomalies(expenses: pd.DataFrame) -> pd.DataFrame:
    """Replace flagged expense amounts with the median of the unflagged ones."""
    work = expenses.copy()
    if work.empty or "is_anomaly" not in work.columns:
        return work
    work["is_anomaly"] = work["is_anomaly"].fillna(False).astype(bool)
    work["category"] = work["category"].fillna("Other").astype(str)
    for category, indexes in work.groupby("category", sort=False).groups.items():
        del category
        subset = work.loc[list(indexes)]
        normal = subset.loc[~subset["is_anomaly"], "amount"]
        median = float(normal.median()) if len(normal) else float(subset["amount"].median())
        hit = subset.index[subset["is_anomaly"].to_numpy()]
        work.loc[hit, "amount"] = median
    return work


def aggregate_spending(expenses: pd.DataFrame, granularity: str) -> pd.Series:
    """Sum expenses by month or by week. Missing periods are filled with zero."""
    if expenses.empty:
        return pd.Series(dtype=float)
    work = expenses.copy()
    work["txn_date"] = pd.to_datetime(work["txn_date"])
    if granularity == "monthly":
        key = work["txn_date"].dt.to_period("M").dt.to_timestamp()
        series = work.groupby(key)["amount"].sum().sort_index()
        full = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    else:
        dates = work["txn_date"]
        key = (dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")).dt.normalize()
        series = work.groupby(key)["amount"].sum().sort_index()
        full = pd.date_range(series.index.min(), series.index.max(), freq="7D")
    return series.reindex(full, fill_value=0.0).astype(float)


def _period_label(timestamp: pd.Timestamp, granularity: str) -> str:
    if granularity == "monthly":
        return pd.Timestamp(timestamp).strftime("%Y-%m")
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def _future_index(last: pd.Timestamp, horizon: int, granularity: str) -> list[pd.Timestamp]:
    labels = []
    current = pd.Timestamp(last)
    for _ in range(horizon):
        if granularity == "monthly":
            month = current.month + 1
            year = current.year + (1 if month == 13 else 0)
            month = 1 if month == 13 else month
            current = pd.Timestamp(year=year, month=month, day=1)
        else:
            current = current + pd.Timedelta(days=7)
        labels.append(current)
    return labels


def _points(
    index: list[pd.Timestamp] | pd.DatetimeIndex, values: np.ndarray, granularity: str
) -> list[dict]:
    return [
        {"period": _period_label(pd.Timestamp(stamp), granularity), "value": round(float(value), 2)}
        for stamp, value in zip(index, values, strict=True)
    ]


def _empty_series() -> dict:
    return {
        "history": [],
        "history_adjusted": [],
        "forecast_raw": [],
        "forecast_adjusted": [],
        "lower": [],
        "upper": [],
        "excluded_periods": [],
        "model_raw": "empty",
        "model_adjusted": "empty",
        "next_raw": None,
        "next_adjusted": None,
    }


def forecast_frame(df: pd.DataFrame, horizon: int, granularity: str, by_category: bool) -> dict:
    """Build the raw vs anomaly-adjusted forecast payload for a user's transactions."""
    overall = _forecast_one(df, horizon, granularity)
    by_cat = None
    if by_category:
        by_cat = {}
        expenses = df[df["type"] == "expense"] if "type" in df.columns else df
        for category in sorted(set(expenses["category"].astype(str))):
            subset = df[df["category"].astype(str) == category]
            by_cat[category] = _forecast_one(subset, horizon, granularity)
    return {
        "granularity": granularity,
        "horizon": horizon,
        "overall": overall,
        "by_category": by_cat,
    }


def _forecast_one(df: pd.DataFrame, horizon: int, granularity: str) -> dict:
    work = df.copy()
    if "type" in work.columns:
        work = work[work["type"] == "expense"]
    if work.empty:
        return _empty_series()
    if "is_anomaly" not in work.columns:
        work["is_anomaly"] = False
    raw = aggregate_spending(work, granularity)
    adjusted_rows = replace_anomalies(work)
    adjusted = aggregate_spending(adjusted_rows, granularity)
    adjusted = adjusted.reindex(raw.index, fill_value=0.0)
    raw_fit = fit_and_forecast(raw.to_numpy(dtype=float), horizon, granularity)
    adj_fit = fit_and_forecast(adjusted.to_numpy(dtype=float), horizon, granularity)
    future = _future_index(pd.Timestamp(raw.index[-1]), horizon, granularity)
    excluded = [
        _period_label(pd.Timestamp(stamp), granularity)
        for stamp in raw.index
        if abs(float(raw.loc[stamp]) - float(adjusted.loc[stamp])) > 0.5
    ]
    return {
        "history": _points(list(raw.index), raw.to_numpy(dtype=float), granularity),
        "history_adjusted": _points(
            list(adjusted.index), adjusted.to_numpy(dtype=float), granularity
        ),
        "forecast_raw": _points(future, raw_fit.point, granularity),
        "forecast_adjusted": _points(future, adj_fit.point, granularity),
        "lower": _points(future, adj_fit.lower, granularity),
        "upper": _points(future, adj_fit.upper, granularity),
        "excluded_periods": excluded,
        "model_raw": raw_fit.model_name,
        "model_adjusted": adj_fit.model_name,
        "next_raw": round(float(raw_fit.point[0]), 2),
        "next_adjusted": round(float(adj_fit.point[0]), 2),
    }


def holdout_errors(
    values: np.ndarray, anomaly_mask: np.ndarray, holdout: int = 3
) -> tuple[float, float, np.ndarray, np.ndarray]:
    """MAE of a raw forecast versus a forecast that replaces flagged training points.

    This is the regression check for the Review 3 bug: a single large outlier in
    the history should hurt the raw forecast more than the adjusted one.
    """
    series = np.asarray(values, dtype=float)
    mask = np.asarray(anomaly_mask, dtype=bool)
    if holdout < 1 or len(series) <= holdout + 2:
        raise ValueError("series is too short for a holdout")
    train_raw = series[:-holdout]
    actual = series[-holdout:]
    train_mask = mask[:-holdout]
    normal = train_raw[~train_mask]
    median = float(np.median(normal if len(normal) else train_raw))
    train_adjusted = train_raw.copy()
    train_adjusted[train_mask] = median
    raw_hat = fit_and_forecast(train_raw, holdout, "monthly").point
    adjusted_hat = fit_and_forecast(train_adjusted, holdout, "monthly").point
    mae_raw = float(np.mean(np.abs(raw_hat - actual)))
    mae_adjusted = float(np.mean(np.abs(adjusted_hat - actual)))
    return mae_raw, mae_adjusted, raw_hat, adjusted_hat


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """MAE, RMSE, and MAPE. MAPE uses a floor of 1 currency unit in the denominator."""
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    error = predicted - actual
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(np.square(error))))
    mape = float(np.mean(np.abs(error) / np.clip(np.abs(actual), 1.0, None)) * 100)
    return {"mae": mae, "rmse": rmse, "mape": mape, "n": float(len(actual))}

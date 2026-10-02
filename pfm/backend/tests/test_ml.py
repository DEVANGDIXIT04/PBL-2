import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.core.rate_limit import enforce_rate_limit, reset_rate_limits
from app.ml.evaluate import classification_metrics, run_evaluation
from app.ml.features import build_features
from app.ml.forecasting import holdout_errors
from app.ml.synthetic_data import generate_transactions


def test_adjusted_forecast_error_is_lower_than_raw():
    """Review 3: an INR 9,500 outlier must not dominate the next-period forecast."""
    series = np.full(18, 3000.0)
    series[14] = 9500.0
    mask = np.zeros(18, dtype=bool)
    mask[14] = True
    mae_raw, mae_adjusted, raw_hat, adjusted_hat = holdout_errors(series, mask, holdout=3)
    assert mae_adjusted < mae_raw
    assert float(np.mean(adjusted_hat)) < float(np.mean(raw_hat))


def test_spike_feature_is_multiple_of_the_usual_amount():
    dates = pd.date_range("2026-01-01", periods=12, freq="7D")
    frame = pd.DataFrame(
        {
            "amount": [400.0] * 11 + [4000.0],
            "category": ["Food"] * 12,
            "merchant": ["Swiggy"] * 12,
            "txn_date": dates,
        }
    )
    features = build_features(frame)
    assert features.loc[11, "amount_over_median"] >= 5


def test_synthetic_data_has_a_small_anomaly_rate():
    frame = generate_transactions(months=12, seed=7)
    rate = float(frame["label"].mean())
    assert 0.015 <= rate <= 0.06
    assert set(frame["category"]) >= {"Salary", "Rent", "Food", "Transport", "Bills", "Shopping"}
    assert frame["amount"].min() > 0


def test_classification_metrics_perfect_split():
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 0, 1, 1])
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    metrics = classification_metrics(y_true, y_pred, scores)
    assert metrics["precision"] == 1
    assert metrics["recall"] == 1
    assert metrics["f1"] == 1
    assert metrics["roc_auc"] == 1
    assert metrics["confusion_matrix"]["tp"] == 2


def test_evaluation_run_produces_metrics():
    payload = run_evaluation(months=8, seed=3, n_estimators=30, origin_estimators=20, write=False)
    assert payload["anomaly"]["product"]["f1"] >= 0
    assert payload["forecast"]["origins"] >= 1
    assert payload["canonical_outlier"]["adjusted_is_better"] is True
    assert {row["model"] for row in payload["anomaly"]["baselines"]} >= {
        "Isolation Forest + MAD (product)",
        "MAD rule",
        "Local Outlier Factor",
        "One-Class SVM",
    }


def test_rate_limiter_blocks_the_eleventh_call():
    reset_rate_limits()
    for _ in range(10):
        enforce_rate_limit("auth:test", limit=10, window_seconds=60, enabled=True)
    try:
        enforce_rate_limit("auth:test", limit=10, window_seconds=60, enabled=True)
        raise AssertionError("expected a 429")
    except HTTPException as exc:
        assert exc.status_code == 429
    enforce_rate_limit("auth:test", limit=10, window_seconds=60, enabled=False)
    reset_rate_limits()

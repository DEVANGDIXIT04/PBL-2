"""Offline evaluation for anomaly detection and anomaly-aware forecasts.

Running this module writes docs/evaluation.md, docs/evaluation_results.json,
and the charts under docs/figures. Every number in those files is computed here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.core.paths import DOCS_DIR, EVALUATION_JSON, EVALUATION_MD, FIGURES_DIR
from app.ml.anomaly_model import score_transactions, train_bundle
from app.ml.features import FEATURE_COLUMNS, build_features
from app.ml.forecasting import (
    aggregate_spending,
    fit_and_forecast,
    holdout_errors,
    regression_metrics,
    replace_anomalies,
)
from app.ml.synthetic_data import generate_transactions


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> dict:
    """Precision, recall, F1, ROC-AUC, PR-AUC, and a confusion matrix."""
    from sklearn.metrics import (
        average_precision_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    actual = np.asarray(y_true).astype(int)
    predicted = np.asarray(y_pred).astype(int)
    ranking = np.asarray(scores, dtype=float)
    matrix = confusion_matrix(actual, predicted, labels=[0, 1])
    result = {
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "support_positive": int(actual.sum()),
        "flagged": int(predicted.sum()),
        "confusion_matrix": {
            "tn": int(matrix[0, 0]),
            "fp": int(matrix[0, 1]),
            "fn": int(matrix[1, 0]),
            "tp": int(matrix[1, 1]),
        },
    }
    if len(np.unique(actual)) > 1 and np.isfinite(ranking).all():
        result["roc_auc"] = float(roc_auc_score(actual, ranking))
        result["pr_auc"] = float(average_precision_score(actual, ranking))
    else:
        result["roc_auc"] = None
        result["pr_auc"] = None
    return result


def _category_stats(amounts: np.ndarray) -> tuple[float, float, float, float]:
    median = float(np.median(amounts))
    mad = float(np.median(np.abs(amounts - median)))
    mean = float(np.mean(amounts))
    std = float(np.std(amounts))
    return median, mad, mean, std


def _rule_scores(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Z-score and MAD scores for the test rows, using training statistics only."""
    z_scores = np.zeros(len(test))
    z_pred = np.zeros(len(test), dtype=int)
    mad_scores = np.zeros(len(test))
    mad_pred = np.zeros(len(test), dtype=int)
    test_categories = test["category"].astype(str).to_numpy()
    test_amounts = test["amount"].to_numpy(dtype=float)
    for category in sorted(set(test_categories)):
        train_amounts = train.loc[train["category"].astype(str) == category, "amount"].to_numpy(
            dtype=float
        )
        indexes = np.flatnonzero(test_categories == category)
        if len(train_amounts) < 3:
            continue
        median, mad, mean, std = _category_stats(train_amounts)
        amounts = test_amounts[indexes]
        if std > 1e-6:
            z_values = (amounts - mean) / std
        else:
            z_values = np.zeros(len(amounts))
        z_scores[indexes] = z_values
        z_pred[indexes] = (z_values > 3).astype(int)
        if mad > 1e-9:
            mad_scores[indexes] = (amounts - median) / mad
            threshold = max(median + 3 * mad, median * 2.0)
            mad_pred[indexes] = (amounts > threshold).astype(int)
        else:
            mad_scores[indexes] = amounts / max(median, 1.0)
            mad_pred[indexes] = (amounts >= median * 3).astype(int)
    return z_pred, z_scores, mad_pred, mad_scores


def evaluate_anomaly(frame: pd.DataFrame, n_estimators: int) -> dict:
    """Temporal holdout: fit on the first 70% of rows, score the last 30%."""
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import OneClassSVM

    ordered = frame.sort_values("txn_date").reset_index(drop=True)
    features = build_features(ordered)
    matrix = features[FEATURE_COLUMNS].to_numpy(dtype=float)
    labels = ordered["label"].to_numpy(dtype=int)
    split = int(len(ordered) * 0.7)
    scaler = StandardScaler()
    x_train = scaler.fit_transform(matrix[:split])
    x_test = scaler.transform(matrix[split:])
    y_test = labels[split:]

    forest = IsolationForest(
        n_estimators=n_estimators, contamination=0.03, random_state=42, n_jobs=1
    )
    forest.fit(x_train)
    if_scores = -np.asarray(forest.decision_function(x_test), dtype=float)
    if_pred = (forest.predict(x_test) == -1).astype(int)

    z_pred, z_scores, mad_pred, mad_scores = _rule_scores(
        ordered.iloc[:split], ordered.iloc[split:]
    )
    combo_pred = np.maximum(if_pred, mad_pred)
    combo_scores = np.maximum(if_scores, mad_scores)

    neighbors = min(20, max(5, len(x_train) // 10))
    lof = LocalOutlierFactor(n_neighbors=neighbors, novelty=True, contamination=0.03)
    lof.fit(x_train)
    lof_scores = -np.asarray(lof.score_samples(x_test), dtype=float)
    lof_pred = (lof.predict(x_test) == -1).astype(int)

    svm = OneClassSVM(kernel="rbf", gamma="scale", nu=0.03)
    svm.fit(x_train)
    svm_scores = -np.asarray(svm.score_samples(x_test), dtype=float)
    svm_pred = (svm.predict(x_test) == -1).astype(int)

    models = [
        ("Isolation Forest + MAD (product)", combo_pred, combo_scores),
        ("Isolation Forest", if_pred, if_scores),
        ("Z-score rule", z_pred, z_scores),
        ("MAD rule", mad_pred, mad_scores),
        ("Local Outlier Factor", lof_pred, lof_scores),
        ("One-Class SVM", svm_pred, svm_scores),
    ]
    rows = []
    for name, pred, scores in models:
        metrics = classification_metrics(y_test, pred, scores)
        metrics["model"] = name
        rows.append(metrics)

    sensitivity = []
    for contamination in (0.01, 0.02, 0.05, 0.1, "auto"):
        candidate = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=42,
            n_jobs=1,
        )
        candidate.fit(x_train)
        scores = -np.asarray(candidate.decision_function(x_test), dtype=float)
        pred = (candidate.predict(x_test) == -1).astype(int)
        metrics = classification_metrics(y_test, pred, scores)
        metrics["contamination"] = contamination
        sensitivity.append(metrics)

    product = rows[0]
    return {
        "protocol": "Fit on the earliest 70% of transactions, score the latest 30%.",
        "test_rows": int(len(y_test)),
        "test_anomalies": int(y_test.sum()),
        "product": product,
        "baselines": rows,
        "sensitivity": sensitivity,
    }


def _month_slices(frame: pd.DataFrame) -> list[pd.Timestamp]:
    dates = pd.to_datetime(frame["txn_date"])
    months = dates.dt.to_period("M").dt.to_timestamp()
    return sorted(pd.Timestamp(value) for value in months.unique())


def evaluate_forecast(frame: pd.DataFrame, origin_estimators: int, min_train: int = 12) -> dict:
    """Rolling-origin monthly forecast comparison on expense totals."""
    ordered = frame.sort_values("txn_date").reset_index(drop=True)
    ordered["txn_date"] = pd.to_datetime(ordered["txn_date"])
    months = _month_slices(ordered)
    collected: dict[str, list[float]] = {
        "naive": [],
        "moving_average": [],
        "exponential_smoothing_raw": [],
        "exponential_smoothing_adjusted": [],
    }
    actuals: list[float] = []
    clean_actuals: list[float] = []
    if len(months) <= min_train:
        min_train = max(6, len(months) // 2)

    for index in range(min_train, len(months)):
        cutoff = months[index]
        nxt = months[index + 1] if index + 1 < len(months) else cutoff + pd.offsets.MonthBegin(1)
        train = ordered[ordered["txn_date"] < cutoff].copy()
        future = ordered[(ordered["txn_date"] >= cutoff) & (ordered["txn_date"] < nxt)]
        future = future[future["type"] == "expense"]
        actual = float(future["amount"].sum()) if len(future) else 0.0
        expenses = train[train["type"] == "expense"]
        if expenses.empty:
            continue
        raw_series = aggregate_spending(expenses, "monthly")
        bundle = train_bundle(train, n_estimators=origin_estimators)
        scored = score_transactions(train, bundle)
        flagged = train.copy()
        flagged["is_anomaly"] = scored["is_anomaly"].to_numpy()
        adjusted_series = aggregate_spending(
            replace_anomalies(flagged[flagged["type"] == "expense"]), "monthly"
        )
        raw_values = raw_series.to_numpy(dtype=float)
        adjusted_values = adjusted_series.reindex(raw_series.index, fill_value=0.0).to_numpy(
            dtype=float
        )
        naive = float(raw_values[-1])
        window = min(3, len(raw_values))
        moving = float(np.mean(raw_values[-window:]))
        raw_forecast = float(fit_and_forecast(raw_values, 1, "monthly").point[0])
        adjusted_forecast = float(fit_and_forecast(adjusted_values, 1, "monthly").point[0])
        collected["naive"].append(naive)
        collected["moving_average"].append(moving)
        collected["exponential_smoothing_raw"].append(raw_forecast)
        collected["exponential_smoothing_adjusted"].append(adjusted_forecast)
        actuals.append(actual)
        if len(future):
            undistorted = future.copy()
            undistorted["is_anomaly"] = undistorted["label"].astype(bool)
            clean_actuals.append(float(replace_anomalies(undistorted)["amount"].sum()))
        else:
            clean_actuals.append(0.0)

    # The forecast is of typical spending. Score it on the next month after labelled
    # spikes are put back to the category median, and keep the raw-total error too.
    return _forecast_tables(collected, actuals, clean_actuals)


def _forecast_tables(
    collected: dict[str, list[float]], actuals: list[float], clean_actuals: list[float]
) -> dict:
    def table_for(target: list[float]) -> tuple[list[dict], dict[str, float]]:
        rows = []
        mape_by_model: dict[str, float] = {}
        actual_array = np.asarray(target, dtype=float)
        for name, preds in collected.items():
            scored = regression_metrics(actual_array, np.asarray(preds, dtype=float))
            mape_by_model[name] = scored["mape"]
            rows.append({"model": name, **scored})
        return rows, mape_by_model

    table, mape_by_model = table_for(clean_actuals)
    raw_table, raw_mape_by_model = table_for(actuals)
    raw_mape = mape_by_model["exponential_smoothing_raw"]
    adjusted_mape = mape_by_model["exponential_smoothing_adjusted"]
    return {
        "protocol": (
            "Monthly expense totals, rolling origin, one-step horizon. "
            "Each origin refits Isolation Forest on past rows only. Flagged amounts are "
            "replaced with the category median only when they are at least three times "
            "that median, then exponential smoothing is fit on the cleaned series. "
            "The main table scores every model on the next month after labelled spikes "
            "are put back to the category median. A second table scores the same forecasts "
            "on the raw total, which still includes those spikes."
        ),
        "origins": len(actuals),
        "models": table,
        "models_vs_raw_actual": raw_table,
        "mape_raw": raw_mape,
        "mape_adjusted": adjusted_mape,
        "mape_raw_vs_raw_actual": raw_mape_by_model["exponential_smoothing_raw"],
        "mape_adjusted_vs_raw_actual": raw_mape_by_model["exponential_smoothing_adjusted"],
        "adjusted_mape_lower": adjusted_mape < raw_mape,
    }


def canonical_outlier_case() -> dict:
    """The Review 3 example: an INR 9,500 spike in an otherwise flat series."""
    series = np.full(18, 3000.0)
    series[14] = 9500.0
    mask = np.zeros(18, dtype=bool)
    mask[14] = True
    mae_raw, mae_adjusted, raw_hat, adjusted_hat = holdout_errors(series, mask, holdout=3)
    return {
        "train_outlier": 9500.0,
        "typical_spend": 3000.0,
        "mae_raw": mae_raw,
        "mae_adjusted": mae_adjusted,
        "adjusted_is_better": mae_adjusted < mae_raw,
        "raw_forecast": [round(float(value), 2) for value in raw_hat],
        "adjusted_forecast": [round(float(value), 2) for value in adjusted_hat],
    }


def run_evaluation(
    months: int = 24,
    seed: int = 42,
    n_estimators: int = 300,
    origin_estimators: int = 100,
    write: bool = True,
) -> dict:
    """Generate data, score models, and optionally write the docs artifacts."""
    frame = generate_transactions(months=months, seed=seed)
    anomaly = evaluate_anomaly(frame, n_estimators=n_estimators)
    forecast = evaluate_forecast(frame, origin_estimators=origin_estimators)
    outlier = canonical_outlier_case()
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "months": months,
        "rows": int(len(frame)),
        "labelled_anomalies": int(frame["label"].sum()),
        "anomaly_rate": float(frame["label"].mean()),
        "n_estimators": n_estimators,
        "origin_estimators": origin_estimators,
        "anomaly": anomaly,
        "forecast": forecast,
        "canonical_outlier": outlier,
        "notes": _forecast_note(forecast, outlier),
    }
    if write:
        _write_outputs(payload)
    return payload


def _forecast_note(forecast: dict, outlier: dict) -> str:
    raw_mape = float(forecast["mape_raw"])
    adjusted_mape = float(forecast["mape_adjusted"])
    if forecast["adjusted_mape_lower"]:
        walk = (
            f"On the synthetic walk-forward, replacing flagged spikes "
            f"(at least three times the category median) lowers MAPE on the undistorted "
            f"next month from {raw_mape:.2f}% to {adjusted_mape:.2f}%. "
            f"Against the raw total, which still includes future spikes, the same forecasts "
            f"score {float(forecast['mape_raw_vs_raw_actual']):.2f}% raw and "
            f"{float(forecast['mape_adjusted_vs_raw_actual']):.2f}% adjusted."
        )
    else:
        walk = (
            f"On the synthetic walk-forward the adjusted MAPE is {adjusted_mape:.2f}% "
            f"and the raw MAPE is {raw_mape:.2f}%."
        )
    return (
        "Anomaly metrics are a temporal holdout, not in-sample scores. "
        f"On the controlled INR 9,500 series, replacing the outlier drops forecast MAE "
        f"from {outlier['mae_raw']:.0f} to {outlier['mae_adjusted']:.0f}. " + walk
    )


def _write_outputs(payload: dict) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    EVALUATION_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _plots(payload)
    EVALUATION_MD.write_text(_markdown(payload), encoding="utf-8")


def _plots(payload: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    baselines = payload["anomaly"]["baselines"]
    names = [row["model"].replace(" (product)", "\n(product)") for row in baselines]
    f1_scores = [row["f1"] for row in baselines]
    figure, axis = plt.subplots(figsize=(9, 4.5))
    colors = ["#0e6b67" if "product" in row["model"] else "#c4b39a" for row in baselines]
    axis.barh(names[::-1], f1_scores[::-1], color=colors[::-1])
    axis.set_xlim(0, 1)
    axis.set_xlabel("F1")
    axis.set_title("Anomaly detection on a temporal holdout")
    figure.tight_layout()
    figure.savefig(FIGURES_DIR / "anomaly_f1.png", dpi=140)
    plt.close(figure)

    forecast_rows = payload["forecast"]["models"]
    figure, axis = plt.subplots(figsize=(8, 4.2))
    axis.bar(
        [row["model"].replace("_", "\n") for row in forecast_rows],
        [row["mape"] for row in forecast_rows],
        color=["#c4b39a", "#c4b39a", "#9f2d2d", "#0e6b67"],
    )
    axis.set_ylabel("MAPE (%)")
    axis.set_title("One-step monthly forecast error")
    figure.tight_layout()
    figure.savefig(FIGURES_DIR / "forecast_mape.png", dpi=140)
    plt.close(figure)

    sensitivity = payload["anomaly"]["sensitivity"]
    figure, axis = plt.subplots(figsize=(7.5, 4.2))
    axis.plot(
        [str(row["contamination"]) for row in sensitivity],
        [row["f1"] for row in sensitivity],
        marker="o",
        color="#0e6b67",
    )
    axis.set_xlabel("Isolation Forest contamination")
    axis.set_ylabel("F1")
    axis.set_title("Sensitivity to contamination")
    figure.tight_layout()
    figure.savefig(FIGURES_DIR / "contamination_sensitivity.png", dpi=140)
    plt.close(figure)


def _fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _markdown(payload: dict) -> str:
    anomaly_rows = payload["anomaly"]["baselines"]
    forecast_rows = payload["forecast"]["models"]
    outlier = payload["canonical_outlier"]
    lines = [
        "# Evaluation",
        "",
        "These figures were produced by `python -m app.ml.evaluate`. They are not hand-written.",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Synthetic rows: {payload['rows']} over {payload['months']} months (seed {payload['seed']})",
        f"- Labelled anomalies: {payload['labelled_anomalies']} ({payload['anomaly_rate']:.1%} of rows)",
        f"- Detector trees: {payload['n_estimators']}. Walk-forward refits use {payload['origin_estimators']} trees.",
        "",
        "## Anomaly detection",
        "",
        payload["anomaly"]["protocol"],
        " The product model uses contamination 0.03, chosen to match the injected anomaly rate. The sweep below includes `auto`.",
        f" Test rows: {payload['anomaly']['test_rows']}. "
        f"Labelled anomalies in the test window: {payload['anomaly']['test_anomalies']}.",
        "",
        "| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | TP | FP | FN | TN |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in anomaly_rows:
        matrix = row["confusion_matrix"]
        lines.append(
            "| {model} | {precision} | {recall} | {f1} | {roc} | {pr} | {tp} | {fp} | {fn} | {tn} |".format(
                model=row["model"],
                precision=_fmt(row["precision"]),
                recall=_fmt(row["recall"]),
                f1=_fmt(row["f1"]),
                roc=_fmt(row["roc_auc"]),
                pr=_fmt(row["pr_auc"]),
                tp=matrix["tp"],
                fp=matrix["fp"],
                fn=matrix["fn"],
                tn=matrix["tn"],
            )
        )
    lines.extend(
        [
            "",
            "![F1 by model](figures/anomaly_f1.png)",
            "",
            "## Contamination sensitivity",
            "",
            "Same holdout, Isolation Forest only, varying `contamination`.",
            "",
            "| Contamination | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for row in payload["anomaly"]["sensitivity"]:
        lines.append(
            f"| {row['contamination']} | {_fmt(row['precision'])} | {_fmt(row['recall'])} | {_fmt(row['f1'])} |"
        )
    lines.extend(
        [
            "",
            "![Contamination sensitivity](figures/contamination_sensitivity.png)",
            "",
            "## Forecasting",
            "",
            payload["forecast"]["protocol"] + f" Origins: {payload['forecast']['origins']}.",
            "",
            "| Model | MAPE % | RMSE | MAE | Origins |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in forecast_rows:
        lines.append(
            f"| {row['model']} | {_fmt(row['mape'], 2)} | {_fmt(row['rmse'], 2)} | "
            f"{_fmt(row['mae'], 2)} | {int(row['n'])} |"
        )
    lines.extend(
        [
            "",
            "![Forecast MAPE](figures/forecast_mape.png)",
            "",
            "Same forecasts scored on the raw next-month total, spikes included.",
            "",
            "| Model | MAPE % | RMSE | MAE | Origins |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["forecast"]["models_vs_raw_actual"]:
        lines.append(
            f"| {row['model']} | {_fmt(row['mape'], 2)} | {_fmt(row['rmse'], 2)} | "
            f"{_fmt(row['mae'], 2)} | {int(row['n'])} |"
        )
    lines.extend(
        [
            "",
            "## The INR 9,500 outlier",
            "",
            "A flat INR 3,000 monthly series with a single INR 9,500 point in the training window, "
            "then three normal months held out. This is the Review 3 failure, measured directly.",
            "",
            f"- Raw forecast MAE: **{outlier['mae_raw']:.2f}**",
            f"- Anomaly-adjusted forecast MAE: **{outlier['mae_adjusted']:.2f}**",
            f"- Adjusted error is lower: **{outlier['adjusted_is_better']}**",
            f"- Raw next points: {outlier['raw_forecast']}",
            f"- Adjusted next points: {outlier['adjusted_forecast']}",
            "",
            "## Reading the numbers",
            "",
            payload["notes"],
            " Duplicate charges of a normal amount are harder than 4–10x spikes, so recall is not 1. "
            "That is the labelled data, not a tuned table.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    run_evaluation()

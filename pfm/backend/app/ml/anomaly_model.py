"""Isolation Forest anomaly model plus a MAD rule and short reasons.

Reasons are built from the two features that deviate most from the category,
not from a fixed sentence per rule.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.features import FEATURE_COLUMNS, build_features

MIN_FIT_ROWS = 30


def mad_mask(df: pd.DataFrame) -> np.ndarray:
    """Flag amounts above the category median plus three MADs.

    When the MAD is zero (a flat category such as rent), only a 3x jump is flagged.
    """
    work = df.reset_index(drop=True)
    flags = np.zeros(len(work), dtype=bool)
    if work.empty:
        return flags
    categories = work["category"].fillna("Other").astype(str)
    amounts = work["amount"].to_numpy(dtype=float)
    for category in categories.unique():
        indexes = np.flatnonzero(categories.to_numpy() == category)
        group = amounts[indexes]
        median = float(np.median(group))
        mad = float(np.median(np.abs(group - median)))
        if mad <= 1e-9:
            threshold = max(median * 3.0, median + 1.0)
        else:
            # 3x MAD, and at least double the usual amount so a tiny MAD
            # (flat bills) does not flag ordinary noise.
            threshold = max(median + 3.0 * mad, median * 2.0)
        flags[indexes] = group > threshold
    return flags


def train_bundle(
    df: pd.DataFrame, budgets: dict[str, float] | None = None, n_estimators: int = 300
) -> dict | None:
    """Fit a scaler and an IsolationForest. Returns None when history is too short."""
    if len(df) < MIN_FIT_ROWS:
        return None
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    features = build_features(df, budgets)
    scaler = StandardScaler()
    matrix = scaler.fit_transform(features[FEATURE_COLUMNS].to_numpy(dtype=float))
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=0.03,
        random_state=42,
        n_jobs=1,
    )
    model.fit(matrix)
    return {
        "model": model,
        "scaler": scaler,
        "feature_columns": list(FEATURE_COLUMNS),
        "version": 1,
        "n_estimators": n_estimators,
    }


def save_bundle(bundle: dict, path: Path) -> None:
    """Persist a trained bundle with joblib."""
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)


def load_bundle(path: Path) -> dict | None:
    """Load a bundle if the file exists."""
    import joblib

    if not path.exists():
        return None
    return joblib.load(path)


def score_transactions(
    df: pd.DataFrame,
    bundle: dict | None,
    budgets: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Score every row. Higher `anomaly_score` means more unusual."""
    work = df.reset_index(drop=True).copy()
    n = len(work)
    result = pd.DataFrame(
        {
            "is_anomaly": np.zeros(n, dtype=bool),
            "anomaly_score": np.zeros(n, dtype=float),
            "anomaly_reason": [None] * n,
        }
    )
    if n == 0:
        return result

    features = build_features(work, budgets)
    rule_flags = mad_mask(work)
    if_flags = np.zeros(n, dtype=bool)
    scores = np.zeros(n, dtype=float)
    if bundle is not None:
        matrix = bundle["scaler"].transform(features[FEATURE_COLUMNS].to_numpy(dtype=float))
        decision = np.asarray(bundle["model"].decision_function(matrix), dtype=float)
        scores = -decision
        if_flags = decision < 0

    flagged = if_flags | rule_flags
    ratios = features["amount_over_median"].to_numpy(dtype=float)
    scores = np.where(rule_flags, np.maximum(scores, 0.05 + ratios / 10.0), scores)
    reasons = _reasons(work, features, flagged)
    result["is_anomaly"] = flagged
    result["anomaly_score"] = np.round(scores, 4)
    result["anomaly_reason"] = reasons
    return result


def _reasons(work: pd.DataFrame, features: pd.DataFrame, flagged: np.ndarray) -> list[str | None]:
    reasons: list[str | None] = [None] * len(work)
    if not flagged.any():
        return reasons
    categories = work["category"].fillna("Other").astype(str)
    for category in categories.unique():
        indexes = np.flatnonzero(categories.to_numpy() == category)
        refs = _category_reference(features.iloc[indexes])
        for index in indexes:
            if not flagged[index]:
                continue
            reasons[index] = _explain_row(features.iloc[index], refs, category)
    return reasons


def _category_reference(features: pd.DataFrame) -> dict[str, tuple[float, float]]:
    refs: dict[str, tuple[float, float]] = {}
    for column in FEATURE_COLUMNS:
        values = features[column].to_numpy(dtype=float)
        median = float(np.median(values))
        scale = float(np.median(np.abs(values - median)))
        refs[column] = (median, max(scale, 0.25))
    return refs


def _explain_row(row: pd.Series, refs: dict[str, tuple[float, float]], category: str) -> str:
    ranked: list[tuple[float, str]] = []
    for column in FEATURE_COLUMNS:
        median, scale = refs[column]
        deviation = abs(float(row[column]) - median) / scale
        ranked.append((deviation, column))
    ranked.sort(reverse=True)
    chosen = [column for deviation, column in ranked[:2] if deviation >= 0.75]
    if not chosen:
        chosen = [ranked[0][1]]
    phrases: list[str] = []
    for column in chosen:
        text = _phrase(column, row, category)
        if text not in phrases:
            phrases.append(text)
    return "; ".join(phrases)


def _phrase(column: str, row: pd.Series, category: str) -> str:
    value = float(row[column])
    if column == "amount_over_median":
        return f"{value:.1f}x the usual {category} spend"
    if column == "new_merchant":
        if value >= 0.5 and float(row["amount_over_median"]) >= 2:
            return "new merchant, high amount"
        if value >= 0.5:
            return "new merchant"
        return "merchant pattern differs from recent history"
    if column == "zscore_90d":
        return f"{abs(value):.1f} standard deviations from recent {category} spending"
    if column == "dow_rarity":
        return "unusual day"
    if column == "hour_rarity":
        return "unusual time"
    if column == "dom_rarity":
        return "unusual day of month"
    if column == "days_since_last":
        if value < 0.2:
            return "possible duplicate charge"
        return f"{value:.1f} days since the last {category} transaction"
    if column == "txns_that_day":
        return "unusually many transactions that day"
    if column == "budget_share":
        return f"high share of the {category} budget"
    if column == "log_amount":
        return "unusually large amount"
    return f"unusual {column.replace('_', ' ')}"

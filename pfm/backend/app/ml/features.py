"""Per-transaction features used by the anomaly model and the rule layer.

Features are computed inside each category from past transactions only, so a
point is not explained by itself. The first few transactions in a category are
treated as neutral so onboarding does not look like fraud.
"""

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "log_amount",
    "zscore_90d",
    "amount_over_median",
    "dow_rarity",
    "dom_rarity",
    "hour_rarity",
    "days_since_last",
    "txns_that_day",
    "new_merchant",
    "budget_share",
]


def build_features(df: pd.DataFrame, budgets: dict[str, float] | None = None) -> pd.DataFrame:
    """Return a feature frame aligned to `df` after a positional reset.

    The caller should pass a frame whose row order is the order it will score.
    """
    work = df.reset_index(drop=True).copy()
    n = len(work)
    data = {column: np.zeros(n, dtype=float) for column in FEATURE_COLUMNS}
    if n == 0:
        return pd.DataFrame(data)

    work["txn_date"] = pd.to_datetime(work["txn_date"])
    work["category"] = work["category"].fillna("Other").astype(str)
    work["merchant"] = work["merchant"].fillna("").astype(str)
    work["amount"] = work["amount"].astype(float)
    budgets = budgets or {}

    day = work["txn_date"].dt.floor("D")
    data["txns_that_day"] = day.map(day.value_counts()).to_numpy(dtype=float)

    for _, indexes in work.groupby("category", sort=False).groups.items():
        ordered = sorted(list(indexes), key=lambda i: (work.at[i, "txn_date"], int(i)))
        past: list[tuple[pd.Timestamp, float]] = []
        seen_merchants: dict[str, int] = {}
        dows: list[int] = []
        doms: list[int] = []
        hours: list[int] = []
        category_name = str(work.at[ordered[0], "category"])
        budget = float(budgets.get(category_name, 0) or 0)

        for position, row_index in enumerate(ordered):
            timestamp = pd.Timestamp(work.at[row_index, "txn_date"])
            amount = float(work.at[row_index, "amount"])
            data["log_amount"][row_index] = float(np.log1p(max(amount, 0.0)))
            window = [value for when, value in past if when >= timestamp - pd.Timedelta(days=90)]
            if len(window) >= 3:
                mean = float(np.mean(window))
                std = float(np.std(window))
                data["zscore_90d"][row_index] = 0.0 if std < 1e-6 else (amount - mean) / std
                median = float(np.median(window))
            elif window:
                median = float(np.median(window))
            else:
                median = max(amount, 1.0)
            data["amount_over_median"][row_index] = amount / median if median > 1e-6 else 1.0

            dow, dom, hour = int(timestamp.dayofweek), int(timestamp.day), int(timestamp.hour)
            merchant = str(work.at[row_index, "merchant"]).strip().lower()
            if position < 3:
                data["days_since_last"][row_index] = 7.0
                data["new_merchant"][row_index] = 0.0
            else:
                data["dow_rarity"][row_index] = 1.0 - (dows.count(dow) / len(dows))
                data["dom_rarity"][row_index] = 1.0 - (doms.count(dom) / len(doms))
                data["hour_rarity"][row_index] = 1.0 - (hours.count(hour) / len(hours))
                data["new_merchant"][row_index] = 0.0 if seen_merchants.get(merchant, 0) else 1.0
                previous = pd.Timestamp(work.at[ordered[position - 1], "txn_date"])
                data["days_since_last"][row_index] = max(
                    (timestamp - previous).total_seconds() / 86400.0, 0.0
                )

            if budget > 0:
                data["budget_share"][row_index] = amount / budget
            else:
                data["budget_share"][row_index] = data["amount_over_median"][row_index]

            seen_merchants[merchant] = seen_merchants.get(merchant, 0) + 1
            past.append((timestamp, amount))
            dows.append(dow)
            doms.append(dom)
            hours.append(hour)

    frame = pd.DataFrame(data).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return frame

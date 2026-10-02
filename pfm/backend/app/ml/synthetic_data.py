"""Seeded synthetic INR transactions with labelled anomalies.

The generator is deterministic for a given seed. Anomalies are about 2–3% of
rows: amount spikes, duplicate charges, unfamiliar merchants, and odd-hour payments.
"""

import calendar
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# End on a complete month so the last bucket is not a two-day stub.
DEFAULT_END = datetime(2026, 9, 30, 20, 0, 0)

FOOD_MERCHANTS = ["Swiggy", "Zomato", "BigBasket", "Local Kirana", "Cafe Coffee Day"]
TRANSPORT_MERCHANTS = ["Uber", "Ola", "Delhi Metro", "Rapido"]
SHOPPING_MERCHANTS = ["Amazon", "Flipkart", "Myntra", "DMart"]


def _month_start(end: datetime, months_back: int) -> datetime:
    """First day of the month that is `months_back` months before `end`."""
    index = end.year * 12 + (end.month - 1) - months_back
    year, month_index = divmod(index, 12)
    return datetime(year, month_index + 1, 1)


def _at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, min(day, last), hour, minute, 0)


def generate_transactions(
    months: int = 18,
    seed: int = 42,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Generate realistic transactions.

    Columns: txn_date, amount, type, category, description, merchant, label.
    `label` is 1 when the row was injected as an anomaly.
    """
    if months < 6:
        raise ValueError("months must be at least 6")
    rng = np.random.default_rng(seed)
    end = end or DEFAULT_END
    rows: list[dict] = []
    for months_back in range(months - 1, -1, -1):
        start = _month_start(end, months_back)
        if start > end:
            continue
        rows.extend(_normal_month(rng, start, end))

    frame = pd.DataFrame(rows)
    frame = _inject_anomalies(frame, rng)
    frame["amount"] = frame["amount"].astype(float).round(2)
    frame["label"] = frame["label"].astype(int)
    return frame.sort_values("txn_date").reset_index(drop=True)


def _add(
    rows: list[dict],
    end: datetime,
    year: int,
    month: int,
    day: int,
    hour: int,
    amount: float,
    txn_type: str,
    category: str,
    description: str,
    merchant: str,
    minute: int = 0,
) -> None:
    txn_date = _at(year, month, day, hour, minute)
    if txn_date > end:
        return
    rows.append(
        {
            "txn_date": txn_date,
            "amount": max(float(amount), 1.0),
            "type": txn_type,
            "category": category,
            "description": description,
            "merchant": merchant,
            "label": 0,
        }
    )


def _normal_month(rng: np.random.Generator, start: datetime, end: datetime) -> list[dict]:
    year, month = start.year, start.month
    rows: list[dict] = []
    _add(
        rows,
        end,
        year,
        month,
        1,
        10,
        80000 + float(rng.normal(0, 600)),
        "income",
        "Salary",
        "Monthly salary",
        "Northwind Labs",
    )
    _add(
        rows,
        end,
        year,
        month,
        3,
        9,
        22000 + float(rng.normal(0, 150)),
        "expense",
        "Rent",
        "House rent",
        "Landlord",
    )
    _add(
        rows,
        end,
        year,
        month,
        6,
        11,
        1900 + float(rng.normal(0, 120)),
        "expense",
        "Bills",
        "Electricity bill",
        "BSES",
    )
    _add(rows, end, year, month, 7, 11, 999, "expense", "Bills", "Broadband", "Airtel")
    _add(rows, end, year, month, 8, 11, 699, "expense", "Bills", "Mobile plan", "Jio")

    for _ in range(int(rng.integers(24, 36))):
        amount = float(np.clip(rng.lognormal(mean=5.9, sigma=0.35), 80, 1200))
        _add(
            rows,
            end,
            year,
            month,
            int(rng.integers(1, 28)),
            int(rng.integers(8, 22)),
            amount,
            "expense",
            "Food",
            "Food",
            str(rng.choice(FOOD_MERCHANTS)),
            minute=int(rng.integers(0, 50)),
        )

    for _ in range(int(rng.integers(10, 16))):
        amount = float(np.clip(rng.normal(180, 60), 40, 500))
        _add(
            rows,
            end,
            year,
            month,
            int(rng.integers(1, 28)),
            int(rng.choice([8, 9, 18, 19, 20])),
            amount,
            "expense",
            "Transport",
            "Commute",
            str(rng.choice(TRANSPORT_MERCHANTS)),
        )

    for _ in range(int(rng.integers(2, 6))):
        amount = float(np.clip(rng.lognormal(mean=7.0, sigma=0.45), 400, 3500))
        _add(
            rows,
            end,
            year,
            month,
            int(rng.integers(1, 28)),
            int(rng.integers(12, 21)),
            amount,
            "expense",
            "Shopping",
            "Shopping",
            str(rng.choice(SHOPPING_MERCHANTS)),
        )
    return rows


def _inject_anomalies(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Turn a small share of later expense rows into labelled anomalies."""
    expenses = frame.index[frame["type"] == "expense"].to_list()
    cutoff = frame["txn_date"].min() + timedelta(days=45)
    eligible = [
        int(index)
        for index in expenses
        if frame.at[index, "txn_date"] >= cutoff
        and frame.at[index, "category"] not in {"Rent", "Bills"}
    ]
    target = min(len(eligible), max(8, int(round(0.025 * len(frame)))))
    chosen = [int(index) for index in rng.choice(eligible, size=target, replace=False)]
    extras: list[dict] = []
    kinds = ["spike", "duplicate", "merchant", "odd_time"]

    for number, index in enumerate(chosen):
        kind = kinds[number % len(kinds)]
        current = frame.loc[index]
        if kind == "spike":
            frame.at[index, "amount"] = float(current["amount"]) * float(rng.uniform(4.0, 10.0))
            frame.at[index, "label"] = 1
            frame.at[index, "description"] = "Unusual spike"
        elif kind == "duplicate":
            frame.at[index, "label"] = 1
            frame.at[index, "description"] = "Duplicate charge"
            extras.append(
                {
                    "txn_date": current["txn_date"] + timedelta(minutes=3),
                    "amount": float(current["amount"]),
                    "type": current["type"],
                    "category": current["category"],
                    "description": "Duplicate charge",
                    "merchant": current["merchant"],
                    "label": 1,
                }
            )
        elif kind == "merchant":
            frame.at[index, "amount"] = float(current["amount"]) * float(rng.uniform(3.0, 6.0))
            frame.at[index, "merchant"] = "UNKNOWN-WIRE"
            frame.at[index, "label"] = 1
            frame.at[index, "description"] = "Unfamiliar merchant"
        else:
            stamp: datetime = current["txn_date"]
            frame.at[index, "txn_date"] = stamp.replace(hour=3, minute=int(rng.integers(0, 40)))
            frame.at[index, "amount"] = float(current["amount"]) * float(rng.uniform(4.0, 8.0))
            frame.at[index, "label"] = 1
            frame.at[index, "description"] = "Odd-hour payment"

    if extras:
        frame = pd.concat([frame, pd.DataFrame(extras)], ignore_index=True)
    return frame

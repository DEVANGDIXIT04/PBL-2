"""Load a user's transactions and build the anomaly-aware forecast."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transaction
from app.ml.forecasting import forecast_frame
from app.services import visible_categories
from app.services.anomaly_service import transactions_frame


def effective_anomaly(row: Transaction) -> bool:
    """Prefer a manual label when the user has confirmed or dismissed the flag."""
    if row.anomaly_label_manual is True:
        return True
    if row.anomaly_label_manual is False:
        return False
    return bool(row.is_anomaly)


def build_forecast(
    db: Session,
    user_id: int,
    *,
    horizon: int,
    granularity: str,
    by_category: bool,
) -> dict:
    """Forecast spending. Flagged anomalies are replaced before the adjusted fit."""
    categories = visible_categories(db, user_id)
    rows = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.txn_date, Transaction.id)
        ).all()
    )
    if not rows:
        empty = forecast_frame(
            pd.DataFrame(columns=["txn_date", "amount", "type", "category", "is_anomaly"]),
            horizon,
            granularity,
            by_category,
        )
        return empty
    frame = transactions_frame(rows, categories)
    frame["is_anomaly"] = [effective_anomaly(row) for row in rows]
    return forecast_frame(frame, horizon, granularity, by_category)

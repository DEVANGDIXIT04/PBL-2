"""Train and apply the per-user anomaly model, with a global cold-start fallback."""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Budget, Category, ModelRun, Transaction, User
from app.db.session import SessionLocal
from app.ml.anomaly_model import load_bundle, save_bundle, score_transactions, train_bundle
from app.ml.synthetic_data import generate_transactions
from app.services import as_utc_naive, visible_categories
from app.services.transaction_service import to_transaction_out

logger = logging.getLogger(__name__)


def model_dir() -> Path:
    """Directory for joblib bundles. Relative paths are resolved from the working directory."""
    settings = get_settings()
    path = Path(settings.model_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def global_model_path() -> Path:
    return model_dir() / "global_iforest.joblib"


def user_model_path(user_id: int) -> Path:
    return model_dir() / f"user_{user_id}_iforest.joblib"


def transactions_frame(rows: list[Transaction], categories: list[Category]) -> pd.DataFrame:
    """Build the modelling frame for one user. Ground-truth labels are not included."""
    names = {category.id: category.name for category in categories}
    return pd.DataFrame(
        [
            {
                "id": row.id,
                "amount": float(row.amount),
                "type": row.type,
                "category": names.get(row.category_id, "Other"),
                "description": row.description or "",
                "merchant": row.merchant or "",
                "txn_date": row.txn_date,
            }
            for row in rows
        ]
    )


def budget_map(db: Session, user_id: int, categories: list[Category]) -> dict[str, float]:
    """Latest budget limit per category name."""
    names = {category.id: category.name for category in categories}
    limits: dict[str, float] = {}
    budgets = db.scalars(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.month)
    ).all()
    for budget in budgets:
        name = names.get(budget.category_id)
        if name:
            limits[name] = float(budget.limit_amount)
    return limits


def record_model_run(
    db: Session,
    user_id: int | None,
    model_type: str,
    params: dict,
    metrics: dict | None = None,
) -> ModelRun:
    """Version a training run. Metrics may be empty until evaluation is attached."""
    run = ModelRun(
        user_id=user_id,
        model_type=model_type,
        params=params,
        metrics=metrics or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_global_bundle(db: Session | None = None, n_estimators: int = 300) -> dict:
    """Load the shared cold-start model, training it on synthetic data the first time."""
    path = global_model_path()
    existing = load_bundle(path)
    if existing is not None:
        return existing
    logger.info("training global isolation forest")
    frame = generate_transactions(months=18, seed=42)
    bundle = train_bundle(frame, n_estimators=n_estimators)
    if bundle is None:
        raise RuntimeError("Global anomaly model could not be trained")
    save_bundle(bundle, path)
    if db is not None:
        record_model_run(
            db,
            None,
            "isolation_forest_global",
            {"n_estimators": n_estimators, "contamination": 0.03, "random_state": 42},
        )
    return bundle


def score_user_transactions(
    db: Session,
    user_id: int,
    *,
    retrain: bool = True,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Re-score one user's transactions.

    Users with at least `min_user_transactions` get their own forest. Everyone else
    is scored with the global model. The MAD rule still uses that user's own amounts.
    """
    settings = get_settings()
    categories = visible_categories(db, user_id)
    rows = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.txn_date, Transaction.id)
        ).all()
    )
    if not rows:
        return {"updated": 0, "anomalies": 0, "model": "none"}

    frame = transactions_frame(rows, categories)
    budgets = budget_map(db, user_id, categories)
    model_name = "global"
    bundle: dict | None
    if len(rows) >= settings.min_user_transactions:
        path = user_model_path(user_id)
        if retrain or not path.exists():
            bundle = train_bundle(frame, budgets, n_estimators=300)
            if bundle is None:
                bundle = get_global_bundle(db)
                model_name = "global"
            else:
                save_bundle(bundle, path)
                record_model_run(
                    db,
                    user_id,
                    "isolation_forest",
                    {
                        "n_estimators": 300,
                        "contamination": 0.03,
                        "random_state": 42,
                        "rows": len(rows),
                    },
                )
                model_name = "user"
        else:
            bundle = load_bundle(path) or get_global_bundle(db)
            model_name = "user" if path.exists() else "global"
    else:
        bundle = get_global_bundle(db)
        model_name = "global"

    scored = score_transactions(frame, bundle, budgets)
    start_naive = as_utc_naive(start) if start else None
    end_naive = as_utc_naive(end) if end else None
    updated = 0
    anomalies = 0
    for position, row in enumerate(rows):
        if start_naive and row.txn_date < start_naive:
            continue
        if end_naive and row.txn_date > end_naive:
            continue
        row.is_anomaly = bool(scored.at[position, "is_anomaly"])
        row.anomaly_score = float(scored.at[position, "anomaly_score"])
        reason = scored.at[position, "anomaly_reason"]
        row.anomaly_reason = None if reason is None or (isinstance(reason, float)) else str(reason)
        updated += 1
        anomalies += int(row.is_anomaly)
    db.commit()
    logger.info(
        "scored user_id=%s updated=%s anomalies=%s model=%s",
        user_id,
        updated,
        anomalies,
        model_name,
    )
    return {"updated": updated, "anomalies": anomalies, "model": model_name}


def list_anomalies(db: Session, user: User) -> list:
    """Return the user's flagged transactions, highest score first."""
    from app.db.models import Category as CategoryModel

    rows = db.execute(
        select(Transaction, CategoryModel.name)
        .join(CategoryModel, CategoryModel.id == Transaction.category_id)
        .where(Transaction.user_id == user.id, Transaction.is_anomaly.is_(True))
        .order_by(Transaction.anomaly_score.desc(), Transaction.txn_date.desc())
    ).all()
    return [to_transaction_out(row, name) for row, name in rows]


def set_manual_label(db: Session, user: User, txn_id: int, is_anomaly: bool):
    """Store the user's own anomaly judgement for later evaluation."""
    row = db.get(Transaction, txn_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    row.anomaly_label_manual = is_anomaly
    db.commit()
    db.refresh(row)
    category = db.get(Category, row.category_id)
    name = category.name if category else "Other"
    return to_transaction_out(row, name)


def train_all_users() -> None:
    """Retrain every user model and the global fallback. Used by the nightly job and the CLI."""
    db = SessionLocal()
    try:
        get_global_bundle(db)
        user_ids = list(db.scalars(select(User.id)).all())
        for user_id in user_ids:
            score_user_transactions(db, int(user_id), retrain=True)
        logger.info("retrained models for %s users", len(user_ids))
    finally:
        db.close()

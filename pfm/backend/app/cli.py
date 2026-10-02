"""Command line: seed, train, evaluate."""

import sys

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Budget, ModelRun, Transaction, User
from app.db.session import SessionLocal, engine
from app.ml.synthetic_data import generate_transactions
from app.services import ensure_default_categories, money, visible_categories
from app.services.anomaly_service import get_global_bundle, score_user_transactions


def seed() -> None:
    """Create the demo user and load a labelled-style synthetic history.

    The command resets the demo user's transactions, budgets, and password so a
    review machine always lands on the same login.
    """
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_categories(db)
        user = db.scalar(select(User).where(User.email == settings.demo_email))
        if user is None:
            user = User(
                email=settings.demo_email, hashed_password=hash_password(settings.demo_password)
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.hashed_password = hash_password(settings.demo_password)
            db.commit()

        db.execute(delete(Transaction).where(Transaction.user_id == user.id))
        db.execute(delete(Budget).where(Budget.user_id == user.id))
        db.execute(delete(ModelRun).where(ModelRun.user_id == user.id))
        db.commit()

        categories = {category.name: category for category in visible_categories(db, user.id)}
        frame = generate_transactions(months=18, seed=42)
        rows = []
        for record in frame.to_dict(orient="records"):
            category = categories[record["category"]]
            stamp = record["txn_date"]
            if hasattr(stamp, "to_pydatetime"):
                stamp = stamp.to_pydatetime().replace(tzinfo=None)
            rows.append(
                Transaction(
                    user_id=user.id,
                    category_id=category.id,
                    amount=money(record["amount"]),
                    type=record["type"],
                    description=str(record["description"]),
                    merchant=str(record["merchant"]),
                    txn_date=stamp,
                    is_anomaly=False,
                )
            )
        db.add_all(rows)
        db.commit()

        food = categories["Food"]
        transport = categories["Transport"]
        shopping = categories["Shopping"]
        for month in ("2026-07", "2026-08", "2026-09"):
            db.add_all(
                [
                    Budget(
                        user_id=user.id, category_id=food.id, month=month, limit_amount=money(12000)
                    ),
                    Budget(
                        user_id=user.id,
                        category_id=transport.id,
                        month=month,
                        limit_amount=money(4000),
                    ),
                    Budget(
                        user_id=user.id,
                        category_id=shopping.id,
                        month=month,
                        limit_amount=money(8000),
                    ),
                ]
            )
        db.commit()
        get_global_bundle(db)
        result = score_user_transactions(db, user.id, retrain=True)
        _label_examples(db, user.id)
        print(f"Demo user: {settings.demo_email} / {settings.demo_password}")
        print(
            f"Transactions: {len(rows)}. Flagged anomalies: {result['anomalies']}. Model: {result['model']}."
        )
    finally:
        db.close()


def _label_examples(db, user_id: int) -> None:
    """Leave a few manual labels so the metrics page has feedback to show."""
    flagged = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id, Transaction.is_anomaly.is_(True))
            .order_by(Transaction.anomaly_score.desc())
            .limit(6)
        ).all()
    )
    for index, row in enumerate(flagged):
        row.anomaly_label_manual = index < 4
    db.commit()


def train() -> None:
    """Retrain the global model and every user model."""
    from app.services.anomaly_service import train_all_users

    Base.metadata.create_all(bind=engine)
    train_all_users()
    print("Training finished.")


def evaluate() -> None:
    """Compute metrics and write docs/evaluation.md."""
    from app.ml.evaluate import run_evaluation

    payload = run_evaluation()
    product = payload["anomaly"]["product"]
    print(
        f"Anomaly F1={product['f1']:.3f} precision={product['precision']:.3f} recall={product['recall']:.3f}"
    )
    print(
        "Forecast MAPE raw="
        f"{payload['forecast']['mape_raw']:.2f} adjusted={payload['forecast']['mape_adjusted']:.2f}"
    )


def main() -> None:
    configure_logging()
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "seed":
        seed()
    elif command == "train":
        train()
    elif command == "evaluate":
        evaluate()
    else:
        print("Usage: python -m app.cli [seed|train|evaluate]")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

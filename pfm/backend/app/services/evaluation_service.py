"""Monthly summary and the evaluation payload shown on the metrics page."""

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.paths import EVALUATION_JSON
from app.db.models import Budget, Category, Transaction
from app.schemas import BudgetUsage, CategorySpend, EvaluationReport, MonthPoint, SummaryReport


def monthly_summary(db: Session, user_id: int, month: str) -> SummaryReport:
    """Income, spend, savings, top categories, budgets, and the anomaly count for one month."""
    start, end = _month_bounds(month)
    rows = db.execute(
        select(Transaction, Category.name)
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.txn_date >= start,
            Transaction.txn_date < end,
        )
    ).all()
    income = 0.0
    expense = 0.0
    by_category: dict[str, float] = defaultdict(float)
    anomaly_count = 0
    for txn, name in rows:
        amount = float(txn.amount)
        if txn.type == "income":
            income += amount
        else:
            expense += amount
            by_category[name] += amount
        if txn.is_anomaly:
            anomaly_count += 1
    savings = income - expense
    top = [
        CategorySpend(category=name, amount=round(amount, 2))
        for name, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True)[:5]
    ]
    budgets = db.execute(
        select(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.user_id == user_id, Budget.month == month)
    ).all()
    usage = []
    for budget, name in budgets:
        spent = round(by_category.get(name, 0.0), 2)
        limit = float(budget.limit_amount)
        usage.append(
            BudgetUsage(
                category=name,
                month=month,
                limit_amount=limit,
                spent=spent,
                usage_ratio=round(spent / limit, 4) if limit else 0.0,
            )
        )
    return SummaryReport(
        month=month,
        income=round(income, 2),
        expense=round(expense, 2),
        savings=round(savings, 2),
        savings_rate=round(savings / income, 4) if income else 0.0,
        top_categories=top,
        budget_usage=usage,
        anomaly_count=anomaly_count,
        trend=_trend(db, user_id, start),
    )


def _trend(db: Session, user_id: int, month_start: datetime) -> list[MonthPoint]:
    """Six months ending at `month_start`."""
    points: list[MonthPoint] = []
    year, month = month_start.year, month_start.month
    keys: list[tuple[int, int]] = []
    for _ in range(6):
        keys.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()
    first_year, first_month = keys[0]
    range_start = datetime(first_year, first_month, 1)
    range_end_year, range_end_month = month_start.year, month_start.month
    if range_end_month == 12:
        range_end = datetime(range_end_year + 1, 1, 1)
    else:
        range_end = datetime(range_end_year, range_end_month + 1, 1)
    rows = db.execute(
        select(Transaction.type, Transaction.amount, Transaction.txn_date).where(
            Transaction.user_id == user_id,
            Transaction.txn_date >= range_start,
            Transaction.txn_date < range_end,
        )
    ).all()
    buckets: dict[str, list[float]] = {f"{y:04d}-{m:02d}": [0.0, 0.0] for y, m in keys}
    for txn_type, amount, txn_date in rows:
        key = f"{txn_date.year:04d}-{txn_date.month:02d}"
        if key not in buckets:
            continue
        if txn_type == "income":
            buckets[key][0] += float(amount)
        else:
            buckets[key][1] += float(amount)
    for key, (income, expense) in buckets.items():
        points.append(MonthPoint(month=key, income=round(income, 2), expense=round(expense, 2)))
    return points


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = (int(part) for part in month.split("-"))
    start = datetime(year, mon, 1)
    end = datetime(year + 1, 1, 1) if mon == 12 else datetime(year, mon + 1, 1)
    return start, end


def feedback_metrics(db: Session, user_id: int) -> dict:
    """Score the model against manual labels when the user has left any."""
    rows = db.execute(
        select(Transaction.is_anomaly, Transaction.anomaly_label_manual).where(
            Transaction.user_id == user_id,
            Transaction.anomaly_label_manual.is_not(None),
        )
    ).all()
    if not rows:
        return {"n_labels": 0}
    from sklearn.metrics import f1_score, precision_score, recall_score

    y_true = [1 if manual else 0 for _flag, manual in rows]
    y_pred = [1 if flag else 0 for flag, _manual in rows]
    return {
        "n_labels": len(rows),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def latest_evaluation(db: Session, user_id: int) -> EvaluationReport:
    """Return the last offline evaluation plus this user's feedback metrics."""
    feedback = feedback_metrics(db, user_id)
    runs = count_model_runs(db, user_id)
    if not EVALUATION_JSON.exists():
        return EvaluationReport(
            available=False,
            user_feedback=feedback,
            model_runs=runs,
            notes="Run make evaluate to generate precision, recall, F1, MAPE, and RMSE.",
        )
    payload = json.loads(EVALUATION_JSON.read_text(encoding="utf-8"))
    anomaly = payload.get("anomaly", {}).get("product", {})
    return EvaluationReport(
        available=True,
        generated_at=payload.get("generated_at"),
        anomaly=anomaly,
        baselines=payload.get("anomaly", {}).get("baselines", []),
        forecast={
            "models": payload.get("forecast", {}).get("models", []),
            "mape_raw": payload.get("forecast", {}).get("mape_raw"),
            "mape_adjusted": payload.get("forecast", {}).get("mape_adjusted"),
            "adjusted_mape_lower": payload.get("forecast", {}).get("adjusted_mape_lower"),
            "canonical_outlier": payload.get("canonical_outlier", {}),
            "origins": payload.get("forecast", {}).get("origins"),
        },
        sensitivity=payload.get("anomaly", {}).get("sensitivity", []),
        user_feedback=feedback,
        model_runs=count_model_runs(db, user_id),
        notes=payload.get("notes", ""),
    )


def count_model_runs(db: Session, user_id: int) -> int:
    """How many stored training runs this user has."""
    from app.db.models import ModelRun

    return int(
        db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.user_id == user_id))
        or 0
    )

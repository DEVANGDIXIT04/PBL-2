"""Transaction, category, and budget operations. Every query is scoped to the user."""

import csv
import io
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Budget, Category, Transaction, User
from app.schemas import (
    BudgetCreate,
    BudgetOut,
    BudgetUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    CsvImportResult,
    CsvRejectedRow,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services import (
    as_utc_naive,
    category_owned_or_global,
    ensure_default_categories,
    money,
    visible_categories,
)

logger = logging.getLogger(__name__)

SORTS = {
    "txn_date": Transaction.txn_date.asc(),
    "amount": Transaction.amount.asc(),
    "created_at": Transaction.created_at.asc(),
    "-txn_date": Transaction.txn_date.desc(),
    "-amount": Transaction.amount.desc(),
    "-created_at": Transaction.created_at.desc(),
}


def to_transaction_out(row: Transaction, category_name: str) -> TransactionOut:
    """Serialize a transaction with its category name."""
    return TransactionOut(
        id=row.id,
        category_id=row.category_id,
        category_name=category_name,
        amount=float(row.amount),
        type=row.type,  # type: ignore[arg-type]
        description=row.description or "",
        merchant=row.merchant or "",
        txn_date=row.txn_date,
        created_at=row.created_at,
        is_anomaly=bool(row.is_anomaly),
        anomaly_score=None if row.anomaly_score is None else float(row.anomaly_score),
        anomaly_reason=row.anomaly_reason,
        anomaly_label_manual=row.anomaly_label_manual,
    )


def _category_for_user(db: Session, user_id: int, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if not category_owned_or_global(category, user_id):
        raise HTTPException(status_code=404, detail="Category not found")
    assert category is not None
    return category


def _rescore(db: Session, user_id: int) -> None:
    """Score the user's transactions. A scoring failure does not roll back the write."""
    try:
        from app.services.anomaly_service import score_user_transactions

        score_user_transactions(db, user_id, retrain=False)
    except Exception:
        logger.exception("anomaly scoring failed")
        db.rollback()


def create_transaction(db: Session, user: User, payload: TransactionCreate) -> TransactionOut:
    """Insert one transaction and refresh anomaly scores."""
    category = _category_for_user(db, user.id, payload.category_id)
    if category.type != payload.type:
        raise HTTPException(status_code=422, detail="Transaction type does not match the category")
    row = Transaction(
        user_id=user.id,
        category_id=category.id,
        amount=money(payload.amount),
        type=payload.type,
        description=payload.description.strip(),
        merchant=payload.merchant.strip(),
        txn_date=as_utc_naive(payload.txn_date),
        is_anomaly=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _rescore(db, user.id)
    db.refresh(row)
    return to_transaction_out(row, category.name)


def list_transactions(
    db: Session,
    user: User,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
    category_id: int | None,
    txn_type: str | None,
    is_anomaly: bool | None,
    page: int,
    page_size: int,
    sort: str,
) -> TransactionPage:
    """Return a page of the user's transactions."""
    if sort not in SORTS:
        raise HTTPException(status_code=422, detail="Unsupported sort field")
    filters = [Transaction.user_id == user.id]
    if start_date is not None:
        filters.append(Transaction.txn_date >= as_utc_naive(start_date))
    if end_date is not None:
        filters.append(Transaction.txn_date <= as_utc_naive(end_date))
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if txn_type is not None:
        filters.append(Transaction.type == txn_type)
    if is_anomaly is not None:
        filters.append(Transaction.is_anomaly.is_(is_anomaly))

    total = int(db.scalar(select(func.count()).select_from(Transaction).where(*filters)) or 0)
    rows = db.execute(
        select(Transaction, Category.name)
        .join(Category, Category.id == Transaction.category_id)
        .where(*filters)
        .order_by(SORTS[sort], Transaction.id.desc())  # type: ignore[arg-type]
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TransactionPage(
        items=[to_transaction_out(row, name) for row, name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_transaction(db: Session, user: User, txn_id: int) -> TransactionOut:
    """Fetch one transaction owned by the user."""
    row, name = _owned_transaction(db, user.id, txn_id)
    return to_transaction_out(row, name)


def update_transaction(
    db: Session, user: User, txn_id: int, payload: TransactionUpdate
) -> TransactionOut:
    """Update fields on a transaction owned by the user."""
    row, _name = _owned_transaction(db, user.id, txn_id)
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"] is not None:
        category = _category_for_user(db, user.id, data["category_id"])
        row.category_id = category.id
    else:
        category = _category_for_user(db, user.id, row.category_id)
    if "type" in data and data["type"] is not None:
        row.type = data["type"]
    if row.type != category.type:
        raise HTTPException(status_code=422, detail="Transaction type does not match the category")
    if "amount" in data and data["amount"] is not None:
        row.amount = money(data["amount"])
    if "description" in data and data["description"] is not None:
        row.description = data["description"].strip()
    if "merchant" in data and data["merchant"] is not None:
        row.merchant = data["merchant"].strip()
    if "txn_date" in data and data["txn_date"] is not None:
        row.txn_date = as_utc_naive(data["txn_date"])
    db.commit()
    _rescore(db, user.id)
    fresh, name = _owned_transaction(db, user.id, txn_id)
    return to_transaction_out(fresh, name)


def delete_transaction(db: Session, user: User, txn_id: int) -> None:
    """Delete a transaction owned by the user."""
    row, _name = _owned_transaction(db, user.id, txn_id)
    db.delete(row)
    db.commit()


def _owned_transaction(db: Session, user_id: int, txn_id: int) -> tuple[Transaction, str]:
    found = db.execute(
        select(Transaction, Category.name)
        .join(Category, Category.id == Transaction.category_id)
        .where(Transaction.id == txn_id, Transaction.user_id == user_id)
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return found[0], found[1]


def import_csv(db: Session, user: User, content: str) -> CsvImportResult:
    """Validate a CSV and insert the rows that pass. Rejected rows are reported, not inserted."""
    ensure_default_categories(db)
    reader = csv.reader(io.StringIO(content))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="CSV is empty") from exc
    columns = {name.strip().lower(): index for index, name in enumerate(header)}
    required = ["date", "amount", "type", "category", "description", "merchant"]
    missing = [name for name in required if name not in columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="CSV must include columns: date, amount, type, category, description, merchant",
        )

    accepted: list[Transaction] = []
    rejected: list[CsvRejectedRow] = []
    for line_no, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        try:
            accepted.append(_row_from_csv(db, user, raw, columns))
        except ValueError as exc:
            rejected.append(CsvRejectedRow(row=line_no, reason=str(exc)))
    db.add_all(accepted)
    db.commit()
    if accepted:
        _rescore(db, user.id)
    logger.info("csv import imported=%s rejected=%s", len(accepted), len(rejected))
    return CsvImportResult(imported=len(accepted), rejected=rejected)


def _row_from_csv(db: Session, user: User, raw: list[str], columns: dict[str, int]) -> Transaction:
    def cell(name: str) -> str:
        index = columns[name]
        if index >= len(raw):
            return ""
        return raw[index].strip()

    txn_type = cell("type").lower()
    if txn_type not in {"income", "expense"}:
        raise ValueError("type must be income or expense")
    category_name = cell("category")
    if not category_name:
        raise ValueError("category is required")
    try:
        amount = float(cell("amount"))
    except ValueError as exc:
        raise ValueError("amount must be a number") from exc
    if amount <= 0:
        raise ValueError("amount must be positive")
    description = cell("description")
    merchant = cell("merchant")
    if len(description) > 500 or len(merchant) > 200 or len(category_name) > 80:
        raise ValueError("a field is too long")
    txn_date = _parse_csv_date(cell("date"))
    category = _category_by_name(db, user, category_name, txn_type)
    return Transaction(
        user_id=user.id,
        category_id=category.id,
        amount=money(amount),
        type=txn_type,
        description=description,
        merchant=merchant,
        txn_date=txn_date,
        is_anomaly=False,
    )


def _parse_csv_date(value: str) -> datetime:
    if not value:
        raise ValueError("date is required")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            if len(value) <= 10:
                parsed = parsed.replace(hour=12)
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("unrecognised date") from exc
    parsed = as_utc_naive(parsed)
    if len(value) <= 10:
        parsed = parsed.replace(hour=12)
    return parsed


def _category_by_name(db: Session, user: User, name: str, txn_type: str) -> Category:
    stmt = select(Category).where(
        func.lower(Category.name) == name.lower(),
        or_(Category.user_id.is_(None), Category.user_id == user.id),
    )
    found = db.scalars(stmt).first()
    if found is not None:
        if found.type != txn_type:
            raise ValueError(f"category {name} is {found.type}, not {txn_type}")
        return found
    created = Category(user_id=user.id, name=name.strip(), type=txn_type)
    db.add(created)
    db.flush()
    return created


def list_categories(db: Session, user: User) -> list[CategoryOut]:
    """Global defaults plus this user's categories."""
    ensure_default_categories(db)
    return [
        CategoryOut(id=category.id, user_id=category.user_id, name=category.name, type=category.type)  # type: ignore[arg-type]
        for category in visible_categories(db, user.id)
    ]


def create_category(db: Session, user: User, payload: CategoryCreate) -> CategoryOut:
    """Create a user-owned category. Names already used by a default are rejected."""
    ensure_default_categories(db)
    name = payload.name.strip()
    taken = db.scalars(
        select(Category).where(
            func.lower(Category.name) == name.lower(),
            or_(Category.user_id.is_(None), Category.user_id == user.id),
        )
    ).first()
    if taken is not None:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(user_id=user.id, name=name, type=payload.type)
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryOut(id=category.id, user_id=category.user_id, name=category.name, type=category.type)  # type: ignore[arg-type]


def update_category(
    db: Session, user: User, category_id: int, payload: CategoryUpdate
) -> CategoryOut:
    """Update a category the user owns. Shared defaults stay fixed."""
    category = _editable_category(db, user.id, category_id)
    if payload.name is not None:
        category.name = payload.name.strip()
    if payload.type is not None:
        category.type = payload.type
    db.commit()
    db.refresh(category)
    return CategoryOut(id=category.id, user_id=category.user_id, name=category.name, type=category.type)  # type: ignore[arg-type]


def delete_category(db: Session, user: User, category_id: int) -> None:
    """Delete a user category that has no transactions."""
    category = _editable_category(db, user.id, category_id)
    in_use = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.category_id == category.id)
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Category still has transactions")
    db.delete(category)
    db.commit()


def _editable_category(db: Session, user_id: int, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or (category.user_id is not None and category.user_id != user_id):
        raise HTTPException(status_code=404, detail="Category not found")
    if category.user_id is None:
        raise HTTPException(status_code=403, detail="Default categories cannot be changed")
    return category


def list_budgets(db: Session, user: User, month: str | None) -> list[BudgetOut]:
    """List budgets, including how much of each limit is already spent."""
    stmt = (
        select(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.user_id == user.id)
        .order_by(Budget.month, Category.name)
    )
    if month is not None:
        stmt = stmt.where(Budget.month == month)
    items = []
    for budget, name in db.execute(stmt).all():
        items.append(_budget_out(db, user.id, budget, name))
    return items


def create_budget(db: Session, user: User, payload: BudgetCreate) -> BudgetOut:
    """Create a monthly category budget."""
    category = _category_for_user(db, user.id, payload.category_id)
    existing = db.scalar(
        select(Budget).where(
            Budget.user_id == user.id,
            Budget.category_id == category.id,
            Budget.month == payload.month,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Budget already exists for that category and month"
        )
    budget = Budget(
        user_id=user.id,
        category_id=category.id,
        month=payload.month,
        limit_amount=money(payload.limit_amount),
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _budget_out(db, user.id, budget, category.name)


def update_budget(db: Session, user: User, budget_id: int, payload: BudgetUpdate) -> BudgetOut:
    """Update a budget owned by the user."""
    budget, name = _owned_budget(db, user.id, budget_id)
    if payload.category_id is not None:
        category = _category_for_user(db, user.id, payload.category_id)
        budget.category_id = category.id
        name = category.name
    if payload.month is not None:
        budget.month = payload.month
    if payload.limit_amount is not None:
        budget.limit_amount = money(payload.limit_amount)
    db.commit()
    db.refresh(budget)
    return _budget_out(db, user.id, budget, name)


def delete_budget(db: Session, user: User, budget_id: int) -> None:
    """Delete a budget owned by the user."""
    budget, _name = _owned_budget(db, user.id, budget_id)
    db.delete(budget)
    db.commit()


def _owned_budget(db: Session, user_id: int, budget_id: int) -> tuple[Budget, str]:
    found = db.execute(
        select(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.id == budget_id, Budget.user_id == user_id)
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return found[0], found[1]


def _budget_out(db: Session, user_id: int, budget: Budget, name: str) -> BudgetOut:
    year, month = (int(part) for part in budget.month.split("-"))
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    spent = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.category_id == budget.category_id,
            Transaction.type == "expense",
            Transaction.txn_date >= start,
            Transaction.txn_date < end,
        )
    )
    spent_value = float(spent or 0)
    limit = float(budget.limit_amount)
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        category_name=name,
        month=budget.month,
        limit_amount=limit,
        spent=round(spent_value, 2),
        usage_ratio=round(spent_value / limit, 4) if limit else 0.0,
    )

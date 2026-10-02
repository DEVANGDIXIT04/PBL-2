"""Shared defaults and small helpers used by services."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Category

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Salary", "income"),
    ("Rent", "expense"),
    ("Food", "expense"),
    ("Transport", "expense"),
    ("Bills", "expense"),
    ("Shopping", "expense"),
    ("Other", "expense"),
]


def as_utc_naive(value: datetime) -> datetime:
    """Convert any datetime to a naive UTC value for storage."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def money(value: float) -> Decimal:
    """Round a number to paise."""
    return Decimal(str(round(float(value), 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_default_categories(db: Session) -> None:
    """Insert global categories once. user_id stays null so every account can use them."""
    existing = {
        name.lower()
        for (name,) in db.execute(select(Category.name).where(Category.user_id.is_(None))).all()
    }
    created = False
    for name, txn_type in DEFAULT_CATEGORIES:
        if name.lower() in existing:
            continue
        db.add(Category(user_id=None, name=name, type=txn_type))
        created = True
    if created:
        db.commit()


def visible_categories(db: Session, user_id: int) -> list[Category]:
    """Global defaults plus categories owned by this user."""
    stmt = (
        select(Category)
        .where(or_(Category.user_id.is_(None), Category.user_id == user_id))
        .order_by(Category.type, Category.name)
    )
    return list(db.scalars(stmt).all())


def category_owned_or_global(category: Category | None, user_id: int) -> bool:
    return category is not None and (category.user_id is None or category.user_id == user_id)

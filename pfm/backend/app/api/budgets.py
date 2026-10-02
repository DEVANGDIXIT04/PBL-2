"""Budget CRUD."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import BudgetCreate, BudgetOut, BudgetUpdate
from app.services import transaction_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    month: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BudgetOut]:
    return transaction_service.list_budgets(db, user, month)


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetOut:
    return transaction_service.create_budget(db, user, payload)


@router.patch("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetOut:
    return transaction_service.update_budget(db, user, budget_id, payload)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    transaction_service.delete_budget(db, user, budget_id)

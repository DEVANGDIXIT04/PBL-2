"""Category CRUD. Defaults are visible to every user and cannot be edited."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import transaction_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CategoryOut]:
    return transaction_service.list_categories(db, user)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return transaction_service.create_category(db, user, payload)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return transaction_service.update_category(db, user, category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    transaction_service.delete_category(db, user, category_id)

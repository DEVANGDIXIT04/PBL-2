"""Transaction CRUD, filters, and CSV import."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import (
    CsvImportResult,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services import transaction_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def list_transactions(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category_id: int | None = None,
    txn_type: str | None = Query(default=None, pattern="^(income|expense)$"),
    is_anomaly: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = "-txn_date",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPage:
    return transaction_service.list_transactions(
        db,
        user,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        txn_type=txn_type,
        is_anomaly=is_anomaly,
        page=page,
        page_size=page_size,
        sort=sort,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return transaction_service.create_transaction(db, user, payload)


@router.post("/import-csv", response_model=CsvImportResult)
async def import_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CsvImportResult:
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=413, detail="CSV is larger than 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8") from exc
    return transaction_service.import_csv(db, user, text)


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(
    txn_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return transaction_service.get_transaction(db, user, txn_id)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int,
    payload: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return transaction_service.update_transaction(db, user, txn_id, payload)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    txn_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    transaction_service.delete_transaction(db, user, txn_id)

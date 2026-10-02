"""Anomaly detection and manual labels."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import AnomalyLabelUpdate, DetectRequest, DetectResult, TransactionOut
from app.services import anomaly_service

router = APIRouter(tags=["anomalies"])


@router.post("/anomalies/detect", response_model=DetectResult)
def detect(
    payload: DetectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    body = payload
    return anomaly_service.score_user_transactions(
        db,
        user.id,
        retrain=body.retrain,
        start=body.start_date,
        end=body.end_date,
    )


@router.get("/anomalies", response_model=list[TransactionOut])
def anomalies(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[TransactionOut]:
    return anomaly_service.list_anomalies(db, user)


@router.patch("/transactions/{txn_id}/anomaly-label", response_model=TransactionOut)
def label_anomaly(
    txn_id: int,
    payload: AnomalyLabelUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return anomaly_service.set_manual_label(db, user, txn_id, payload.is_anomaly)

"""Monthly summary and published model metrics."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import EvaluationReport, SummaryReport
from app.services.evaluation_service import latest_evaluation, monthly_summary

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=SummaryReport)
def summary(
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryReport:
    return monthly_summary(db, user.id, month)


@router.get("/evaluation", response_model=EvaluationReport)
def evaluation(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> EvaluationReport:
    return latest_evaluation(db, user.id)

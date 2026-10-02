"""Spending forecast with the raw and anomaly-adjusted series."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import ForecastResponse
from app.services.forecast_service import build_forecast

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("", response_model=ForecastResponse)
def forecast(
    horizon: int = Query(default=1, ge=1, le=6),
    granularity: str = Query(default="monthly", pattern="^(monthly|weekly)$"),
    by_category: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return build_forecast(
        db,
        user.id,
        horizon=horizon,
        granularity=granularity,
        by_category=by_category,
    )

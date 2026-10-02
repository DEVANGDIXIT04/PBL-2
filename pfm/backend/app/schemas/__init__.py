"""Pydantic schemas for the HTTP API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TxnType = Literal["income", "expense"]


class ErrorBody(BaseModel):
    detail: str
    code: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.access",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.refresh",
                "token_type": "bearer",
            }
        }
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "demo@example.com", "password": "Demo1234!"}}
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "demo@example.com", "password": "Demo1234!"}}
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: TxnType

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Coffee", "type": "expense"}})


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    type: TxnType | None = None


class CategoryOut(BaseModel):
    id: int
    user_id: int | None
    name: str
    type: TxnType


class TransactionCreate(BaseModel):
    category_id: int
    amount: float = Field(gt=0, le=9_999_999_999)
    type: TxnType
    description: str = Field(default="", max_length=500)
    merchant: str = Field(default="", max_length=200)
    txn_date: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category_id": 3,
                "amount": 450.0,
                "type": "expense",
                "description": "Dinner",
                "merchant": "Swiggy",
                "txn_date": "2026-03-14T20:15:00",
            }
        }
    )


class TransactionUpdate(BaseModel):
    category_id: int | None = None
    amount: float | None = Field(default=None, gt=0, le=9_999_999_999)
    type: TxnType | None = None
    description: str | None = Field(default=None, max_length=500)
    merchant: str | None = Field(default=None, max_length=200)
    txn_date: datetime | None = None


class TransactionOut(BaseModel):
    id: int
    category_id: int
    category_name: str
    amount: float
    type: TxnType
    description: str
    merchant: str
    txn_date: datetime
    created_at: datetime
    is_anomaly: bool
    anomaly_score: float | None
    anomaly_reason: str | None
    anomaly_label_manual: bool | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class CsvRejectedRow(BaseModel):
    row: int
    reason: str


class CsvImportResult(BaseModel):
    imported: int
    rejected: list[CsvRejectedRow]


class AnomalyLabelUpdate(BaseModel):
    is_anomaly: bool

    model_config = ConfigDict(json_schema_extra={"example": {"is_anomaly": False}})


class DetectRequest(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    retrain: bool = True


class DetectResult(BaseModel):
    updated: int
    anomalies: int
    model: str


class BudgetCreate(BaseModel):
    category_id: int
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    limit_amount: float = Field(gt=0, le=9_999_999_999)

    model_config = ConfigDict(
        json_schema_extra={"example": {"category_id": 3, "month": "2026-03", "limit_amount": 8000}}
    )


class BudgetUpdate(BaseModel):
    limit_amount: float | None = Field(default=None, gt=0, le=9_999_999_999)
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    category_id: int | None = None


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category_name: str
    month: str
    limit_amount: float
    spent: float = 0
    usage_ratio: float = 0


class ForecastPoint(BaseModel):
    period: str
    value: float


class ForecastSeries(BaseModel):
    history: list[ForecastPoint]
    history_adjusted: list[ForecastPoint]
    forecast_raw: list[ForecastPoint]
    forecast_adjusted: list[ForecastPoint]
    lower: list[ForecastPoint]
    upper: list[ForecastPoint]
    excluded_periods: list[str]
    model_raw: str
    model_adjusted: str
    next_raw: float | None = None
    next_adjusted: float | None = None


class ForecastResponse(BaseModel):
    granularity: Literal["monthly", "weekly"]
    horizon: int
    overall: ForecastSeries
    by_category: dict[str, ForecastSeries] | None = None


class CategorySpend(BaseModel):
    category: str
    amount: float


class BudgetUsage(BaseModel):
    category: str
    month: str
    limit_amount: float
    spent: float
    usage_ratio: float


class MonthPoint(BaseModel):
    month: str
    income: float
    expense: float


class SummaryReport(BaseModel):
    month: str
    income: float
    expense: float
    savings: float
    savings_rate: float
    top_categories: list[CategorySpend]
    budget_usage: list[BudgetUsage]
    anomaly_count: int
    trend: list[MonthPoint]


class EvaluationReport(BaseModel):
    available: bool
    generated_at: str | None = None
    anomaly: dict = Field(default_factory=dict)
    baselines: list = Field(default_factory=list)
    forecast: dict = Field(default_factory=dict)
    sensitivity: list = Field(default_factory=list)
    user_feedback: dict | None = None
    model_runs: int = 0
    notes: str = ""

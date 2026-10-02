"""Register, login, refresh, and the current user."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_current_user
from app.core.rate_limit import limit_auth
from app.core.security import (
    TokenError,
    decode_token,
    hash_password,
    issue_token_pair,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.services import ensure_default_categories

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "content": {
                "application/json": {
                    "example": {"detail": "Email already registered", "code": "conflict"}
                }
            }
        }
    },
)
def register(
    payload: RegisterRequest, request: Request, db: Session = Depends(get_db)
) -> TokenPair:
    limit_auth(request)
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=payload.email.lower(), hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_default_categories(db)
    return TokenPair(**issue_token_pair(user.id))


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    limit_auth(request)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenPair(**issue_token_pair(user.id))


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    limit_auth(request)
    try:
        decoded = decode_token(payload.refresh_token, "refresh")
        user_id = int(decoded["sub"])
    except (TokenError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return TokenPair(**issue_token_pair(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user

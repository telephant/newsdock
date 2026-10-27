"""Sign-up and login routes (C-13, ADR-0020).

Plain `def` routes: FastAPI runs them in its thread pool, which is where the
~25 ms argon2 hash belongs. Errors carry stable codes in `detail`. The same 401
body answers an unknown email and a wrong password (AC-5). Neither passwords,
cookie values nor hashes are logged; INFO lines carry the user id and role only.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from newsdock_api.domain.accounts import (
    AccountStore,
    DuplicateEmail,
    InvalidCredentials,
    InvalidEmail,
    PasswordHasher,
    SignupClosed,
    WeakPassword,
    check_password,
    ensure_signup_open,
    hash_token,
    new_session_token,
    normalize_email,
    session_expiry,
    verify_login,
)
from newsdock_api.domain.loginlimit import LoginLimiter

logger = logging.getLogger(__name__)

BODY_LIMIT = 1024  # characters; real bounds are enforced by the domain policy


class Credentials(BaseModel):
    email: str = Field(max_length=BODY_LIMIT)
    password: str = Field(max_length=BODY_LIMIT)


class PublicUser(BaseModel):
    id: str
    email: str
    role: str


def build_accounts_router(
    store: AccountStore,
    hasher: PasswordHasher,
    limiter: LoginLimiter,
    *,
    dummy_hash: str,
    signup_open: bool,
    min_password_length: int,
    cookie_name: str,
    cookie_secure: bool,
    session_idle: timedelta,
    session_absolute: timedelta,
) -> APIRouter:
    router = APIRouter(prefix="/api/auth")

    @router.post("/signup", status_code=201)
    def signup(body: Credentials) -> PublicUser:
        try:
            ensure_signup_open(signup_open)
        except SignupClosed as exc:
            raise HTTPException(status_code=403, detail="signup_closed") from exc
        try:
            email = normalize_email(body.email)
            check_password(body.password, min_length=min_password_length)
        except InvalidEmail as exc:
            raise HTTPException(status_code=422, detail="invalid_email") from exc
        except WeakPassword as exc:
            raise HTTPException(status_code=422, detail="invalid_password") from exc
        try:
            user = store.create_user(email, hasher.hash(body.password))
        except DuplicateEmail as exc:
            raise HTTPException(status_code=409, detail="email_taken") from exc
        except SQLAlchemyError as exc:
            logger.exception("signup failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        logger.info("signup user=%s role=%s", user.id, user.role.value)
        return PublicUser(id=user.id, email=user.email, role=user.role.value)

    @router.post("/login")
    def login(body: Credentials, response: Response) -> PublicUser:
        key = body.email  # the limiter normalizes; unknown emails count too
        decision = limiter.check(key)
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="too_many_attempts",
                headers={"Retry-After": str(decision.retry_after)},
            )
        try:
            result = verify_login(store, hasher, body.email, body.password, dummy_hash)
        except InvalidCredentials as exc:
            limiter.record_failure(key)
            logger.info("login failed")
            raise HTTPException(status_code=401, detail="invalid_credentials") from exc
        except SQLAlchemyError as exc:
            logger.exception("login lookup failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        limiter.clear(key)
        user = result.user
        now = datetime.now(UTC)
        token = new_session_token()
        try:
            if result.rehash:
                store.set_password_hash(user.id, hasher.hash(body.password))
            store.create_session(
                user.id, hash_token(token), now, session_expiry(now, session_absolute)
            )
            store.delete_expired(now, session_idle)
        except SQLAlchemyError as exc:
            logger.exception("login session failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        response.set_cookie(
            cookie_name,
            token,
            max_age=int(session_absolute.total_seconds()),
            httponly=True,
            samesite="lax",
            secure=cookie_secure,
            path="/",
        )
        logger.info("login user=%s role=%s", user.id, user.role.value)
        return PublicUser(id=user.id, email=user.email, role=user.role.value)

    return router

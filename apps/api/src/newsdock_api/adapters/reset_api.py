"""Password reset routes (C-43, ADR-0026/0027): forgot, reset and options.

The foreground of `forgot-password` does the feature check, the email format, the
limiters and the scheduling, and nothing that touches the database, so a known and an
unknown email cost the same and both answer 202 `{"ok": true}`. The lookup, the code,
the upsert and the mail run in a background job whose errors never reach the client.
`reset-password` follows design-detail §4 step by step and has one refusal,
400 `invalid_or_expired_code`. Logs carry the user id and the outcome only: never the
code, the address or a password.
"""

import logging
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from newsdock_api.domain.accounts import (
    InvalidEmail,
    PasswordHasher,
    UserLookup,
    WeakPassword,
    check_password,
    normalize_email,
)
from newsdock_api.domain.loginlimit import LoginLimiter
from newsdock_api.domain.mail import Mailer, MailError
from newsdock_api.domain.passwordreset import (
    CODE_PATTERN,
    DUMMY_USER_ID,
    ResetStore,
    code_expiry,
    hash_code,
    matches,
    new_code,
    reset_mail,
)
from newsdock_api.domain.resetlimit import ResetAttemptLimiter, ResetRequestLimiter
from newsdock_api.domain.signuplimit import UNKNOWN_ADDRESS

logger = logging.getLogger(__name__)

BODY_LIMIT = 1024
UNAVAILABLE = "password_reset_unavailable"
_DUMMY_HASH = "0" * 64


class ForgotBody(BaseModel):
    email: str = Field(max_length=BODY_LIMIT)


class ResetBody(BaseModel):
    email: str = Field(max_length=BODY_LIMIT)
    code: str = Field(max_length=BODY_LIMIT)
    password: str = Field(max_length=BODY_LIMIT)


class AuthOptions(BaseModel):
    password_reset_enabled: bool


def build_reset_router(
    users: UserLookup,
    resets: ResetStore,
    hasher: PasswordHasher,
    login_limiter: LoginLimiter,
    request_limiter: ResetRequestLimiter,
    attempt_limiter: ResetAttemptLimiter,
    mailer: Mailer | None,
    *,
    enabled: bool,
    secret: str,
    code_minutes: int,
    max_attempts: int,
    min_password_length: int,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/api/auth")

    def unavailable() -> HTTPException:
        return HTTPException(status_code=503, detail=UNAVAILABLE)

    def refused() -> HTTPException:
        return HTTPException(status_code=400, detail="invalid_or_expired_code")

    def issue_and_send(email: str) -> None:
        """Background job: look the user up, store a code, mail it. Never raises."""
        if mailer is None:
            return
        try:
            user = users.find_by_email(email)
            if user is None:
                return
            now = clock()
            code = new_code()
            code_hash = hash_code(secret, user.id, code)
            resets.delete_expired(now)
            resets.issue(user.id, code_hash, code_expiry(now, code_minutes), now)
            try:
                mailer.send(user.email, *reset_mail(code, code_minutes))
            except MailError as exc:
                resets.discard(user.id, code_hash)
                logger.warning("reset mail failed user=%s kind=%s", user.id, exc)
                return
            logger.info("reset issued user=%s", user.id)
        except Exception as exc:  # the client already has its answer
            logger.error("reset issue failed kind=%s", type(exc).__name__)

    @router.get("/options")
    def options() -> AuthOptions:
        return AuthOptions(password_reset_enabled=enabled)

    @router.post("/forgot-password", status_code=202)
    def forgot_password(
        body: ForgotBody, request: Request, background: BackgroundTasks
    ) -> dict[str, bool]:
        if not enabled:
            raise unavailable()
        try:
            email = normalize_email(body.email)
        except InvalidEmail as exc:
            raise HTTPException(status_code=422, detail="invalid_email") from exc
        address = request.client.host if request.client else UNKNOWN_ADDRESS
        decision = request_limiter.attempt(email, address)
        if not decision.allowed:
            logger.info("reset request limited")
            raise HTTPException(
                status_code=429,
                detail="too_many_reset_requests",
                headers={"Retry-After": str(decision.retry_after)},
            )
        background.add_task(issue_and_send, email)
        return {"ok": True}

    @router.post("/reset-password", status_code=204)
    def reset_password(body: ResetBody, request: Request) -> Response:
        if not enabled:
            raise unavailable()
        try:
            email = normalize_email(body.email)
            check_password(body.password, min_length=min_password_length)
        except InvalidEmail as exc:
            raise HTTPException(status_code=422, detail="invalid_email") from exc
        except WeakPassword as exc:
            raise HTTPException(status_code=422, detail="invalid_password") from exc
        address = request.client.host if request.client else UNKNOWN_ADDRESS
        decision = attempt_limiter.attempt(address)
        if not decision.allowed:
            logger.info("reset attempt limited")
            raise HTTPException(
                status_code=429,
                detail="too_many_reset_attempts",
                headers={"Retry-After": str(decision.retry_after)},
            )
        if CODE_PATTERN.fullmatch(body.code) is None:
            raise refused()
        try:
            user = users.find_by_email(email)
            if user is None:
                matches(_DUMMY_HASH, secret, DUMMY_USER_ID, body.code)
                raise refused()
            stored = resets.claim_attempt(user.id, clock(), max_attempts)
            if stored is None:
                matches(_DUMMY_HASH, secret, DUMMY_USER_ID, body.code)
                raise refused()
            if not matches(stored, secret, user.id, body.code):
                raise refused()
            if not resets.complete(user.id, stored, hasher.hash(body.password)):
                raise refused()
        except SQLAlchemyError as exc:
            logger.error("password reset failed kind=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="unavailable") from exc
        login_limiter.clear(email)
        logger.info("reset done user=%s", user.id)
        return Response(status_code=204)

    return router

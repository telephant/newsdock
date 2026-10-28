"""Sign-up and login routes (C-13, ADR-0020).

Plain `def` routes: FastAPI runs them in its thread pool, which is where the
~25 ms argon2 hash belongs. Errors carry stable codes in `detail`. The same 401
body answers an unknown email and a wrong password (AC-5). Neither passwords,
cookie values nor hashes are logged; INFO lines carry the user id and role only.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from newsdock_api.domain.accounts import (
    AccountStore,
    DuplicateEmail,
    InvalidCredentials,
    InvalidEmail,
    LastOwner,
    PasswordHasher,
    Role,
    SignupClosed,
    UserAdminStore,
    UserPrincipal,
    UserSummary,
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
from newsdock_api.domain.signuplimit import UNKNOWN_ADDRESS, SignupLimiter

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
    signup_limiter: SignupLimiter,
    *,
    require_user: Callable[[Request], UserPrincipal],
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
    def signup(body: Credentials, request: Request) -> PublicUser:
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
        # Only requests that passed the checks above count, and a refusal comes
        # before the argon2 hash and the database write (signup-rate-limit D-3).
        # The socket peer address is used; X-Forwarded-For is forgeable (D-6).
        address = request.client.host if request.client else UNKNOWN_ADDRESS
        decision = signup_limiter.attempt(address)
        if not decision.allowed:
            logger.info("signup limited")
            raise HTTPException(
                status_code=429,
                detail="too_many_signups",
                headers={"Retry-After": str(decision.retry_after)},
            )
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

    @router.get("/me")
    def me(user: Annotated[UserPrincipal, Depends(require_user)]) -> PublicUser:
        return PublicUser(id=user.user_id, email=user.email, role=user.role.value)

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        """End the session named by the cookie; 204 even if it was already gone."""
        token = request.cookies.get(cookie_name)
        if not token:
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            store.delete_session(hash_token(token))
        except SQLAlchemyError as exc:
            logger.exception("logout failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        response = Response(status_code=204)
        response.delete_cookie(
            cookie_name, path="/", httponly=True, samesite="lax", secure=cookie_secure
        )
        logger.info("logout")
        return response

    return router


class RoleChange(BaseModel):
    role: Role


def build_users_router(
    users: UserAdminStore, require_owner: Callable[[Request], UserPrincipal]
) -> APIRouter:
    """Owner-only user management (AC-9, AC-10); every route needs `manage_users`."""
    router = APIRouter(prefix="/api/users", dependencies=[Depends(require_owner)])

    @router.get("")
    def list_users() -> list[UserSummary]:
        try:
            return users.list_users()
        except SQLAlchemyError as exc:
            logger.exception("list users failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc

    @router.patch("/{user_id}")
    def change_role(user_id: str, body: RoleChange) -> PublicUser:
        try:
            changed = users.set_role(user_id, body.role)
            updated = users.get_by_id(user_id) if changed else None
        except LastOwner as exc:
            raise HTTPException(status_code=409, detail="last_owner") from exc
        except SQLAlchemyError as exc:
            logger.exception("role change failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="not_found")
        logger.info("role change user=%s role=%s", updated.id, updated.role.value)
        return PublicUser(id=updated.id, email=updated.email, role=updated.role.value)

    @router.delete("/{user_id}", status_code=204)
    def delete_user(user_id: str) -> Response:
        try:
            deleted = users.delete_user(user_id)
        except LastOwner as exc:
            raise HTTPException(status_code=409, detail="last_owner") from exc
        except SQLAlchemyError as exc:
            logger.exception("user delete failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="not_found")
        logger.info("user deleted user=%s", user_id)
        return Response(status_code=204)

    return router


class PasswordReset(BaseModel):
    email: str = Field(max_length=BODY_LIMIT)
    password: str = Field(max_length=BODY_LIMIT)


def build_recovery_router(
    store: AccountStore,
    hasher: PasswordHasher,
    limiter: LoginLimiter,
    *,
    require_token: Callable[[Request], None],
    min_password_length: int,
) -> APIRouter:
    """Owner recovery (C-17, AC-16): token-only, so no session can take an account."""
    router = APIRouter(prefix="/api/admin/users", dependencies=[Depends(require_token)])

    @router.post("/reset-password", status_code=204)
    def reset_password(body: PasswordReset) -> Response:
        try:
            email = normalize_email(body.email)
            check_password(body.password, min_length=min_password_length)
        except InvalidEmail as exc:
            raise HTTPException(status_code=422, detail="invalid_email") from exc
        except WeakPassword as exc:
            raise HTTPException(status_code=422, detail="invalid_password") from exc
        try:
            user = store.find_by_email(email)
            if user is None:
                raise HTTPException(status_code=404, detail="not_found")
            store.set_password_hash(user.id, hasher.hash(body.password))
            ended = store.delete_user_sessions(user.id)
        except SQLAlchemyError as exc:
            logger.exception("password reset failed")
            raise HTTPException(status_code=503, detail="unavailable") from exc
        limiter.clear(email)  # a locked-out owner is the case this exists for
        logger.info("password reset user=%s sessions_ended=%d", user.id, ended)
        return Response(status_code=204)

    return router

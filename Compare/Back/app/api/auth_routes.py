from __future__ import annotations

from fastapi import APIRouter, Request, Response
from app.api.dependencies import AuthenticatedPrincipal, AuthenticationServiceDependency
from app.api.responses import success
from app.contracts.authentication import AuthenticatedAccount, LoginRequest, LogoutResult
from app.contracts.envelope import ApiEnvelope, ErrorEnvelope
from app.services.authentication import SESSION_COOKIE_NAME

router = APIRouter(prefix="/auth", tags=["authentication"])
AUTH_ERRORS = {401: {"model": ErrorEnvelope, "description": "Authentication required or failed"}}

@router.post("/login", response_model=ApiEnvelope[AuthenticatedAccount], responses=AUTH_ERRORS, operation_id="login")
def login(request: Request, response: Response, payload: LoginRequest, service: AuthenticationServiceDependency) -> dict[str, object]:
    settings = request.app.state.settings
    account, token, expires_at = service.login(
        payload.username,
        payload.password,
        revoke_existing_sessions=settings.environment.strip().lower() == "production",
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME, value=token, httponly=True, secure=settings.session_cookie_secure,
        samesite="strict", expires=expires_at, path="/",
    )
    return success(request, account)

@router.get("/me", response_model=ApiEnvelope[AuthenticatedAccount], responses=AUTH_ERRORS, operation_id="readCurrentAccount")
def me(request: Request, principal: AuthenticatedPrincipal) -> dict[str, object]:
    return success(request, principal)

@router.post("/logout", response_model=ApiEnvelope[LogoutResult], operation_id="logout")
def logout(request: Request, response: Response, service: AuthenticationServiceDependency) -> dict[str, object]:
    service.logout(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return success(request, LogoutResult())

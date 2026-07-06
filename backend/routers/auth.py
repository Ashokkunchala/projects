"""Auth routes — signup, login, logout, me, change-password."""

import logging
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from main import (
    AuthRequest,
    ChangePasswordRequest,
    JWT_EXPIRY_HOURS,
    LoginRequest,
    _COOKIE_SECURE,
    _check_rate_limit,
    _create_token,
    _verify_token,
    db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="")


@router.post("/api/auth/signup", status_code=201)
async def signup(req: AuthRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"signup:ip:{ip}", max_attempts=10, window_seconds=300)
    await _check_rate_limit(f"signup:email:{req.email}", max_attempts=5, window_seconds=300)

    existing = await db.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="This email is already signed up. Please try with a new email ID or reach out to the admin.")

    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user = await db.create_user(req.email, pw_hash)
    if not user:
        raise HTTPException(status_code=500, detail="Could not create user")

    token = _create_token(user["id"], user["email"])
    response.set_cookie(
        "token", token,
        httponly=True, samesite="strict", secure=_COOKIE_SECURE,
        max_age=JWT_EXPIRY_HOURS * 3600,
    )

    # Send welcome email
    try:
        from notifications import send_email
        await send_email(
            to=req.email,
            subject="Welcome to Cloud Cost Detective!",
            body_text=f"Welcome to Cloud Cost Detective!\n\n"
                      f"Your account has been created successfully. You can now scan your AWS, Azure, and GCP accounts "
                      f"to detect cost-saving opportunities.\n\n"
                      f"Get started: {request.base_url}\n\n"
                      f"Pro tip: Configure your AI provider (Google Gemini, Claude, GPT-4o) in the Settings panel "
                      f"for AI-powered cost analysis.\n\n"
                      f"Happy cost hunting!\n"
                      f"The Cost Detective Team",
            body_html=f"<h2>Welcome to Cloud Cost Detective!</h2>"
                      f"<p>Your account has been created successfully. You can now scan your AWS, Azure, and GCP "
                      f"accounts to detect cost-saving opportunities.</p>"
                      f"<p><a href=\"{request.base_url}\" style=\"display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;text-decoration:none;border-radius:8px;\">Get Started</a></p>"
                      f"<p><strong>Pro tip:</strong> Configure your AI provider (Google Gemini, Claude, GPT-4o) "
                      f"in the Settings panel for AI-powered cost analysis.</p>",
        )
    except Exception as e:
        logger.warning("welcome_email.failed", extra={"error": str(e), "email": req.email})

    return {"user": {"id": user["id"], "email": user["email"]}}


@router.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    from main import _DUMMY_HASH

    ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"login:ip:{ip}", max_attempts=20, window_seconds=60)
    await _check_rate_limit(f"login:email:{req.email}", max_attempts=10, window_seconds=60)

    user = await db.get_user_by_email(req.email)

    stored_hash = user["password_hash"].encode() if user else _DUMMY_HASH.encode()
    password_ok = bcrypt.checkpw(req.password.encode(), stored_hash)

    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email address.")
    if not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect password.")

    token = _create_token(user["id"], user["email"])
    response.set_cookie(
        "token", token,
        httponly=True, samesite="strict", secure=_COOKIE_SECURE,
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    return {"user": {"id": user["id"], "email": user["email"]}}


@router.post("/api/auth/logout")
async def logout(response: Response, user_info: dict = Depends(_verify_token)):
    jti = user_info.get("jti")
    if jti:
        exp = user_info.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await db.revoke_token(jti, expires_at)
    response.delete_cookie("token", samesite="strict")
    return {"status": "logged out"}


@router.get("/api/auth/me")
async def get_me(user_info: dict = Depends(_verify_token)):
    user = await db.get_user_by_id(user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "email": user["email"]}


@router.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"change-password:{user_info['user_id']}", max_attempts=5, window_seconds=300)

    user = await db.get_user_by_id(user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(req.current_password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    await db.update_user_password(user_info["user_id"], new_hash)
    return {"message": "Password updated successfully"}

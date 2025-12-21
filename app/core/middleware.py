from fastapi import Request, Response
import jwt
from datetime import timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import MutableHeaders
import secrets
from app.core.config import settings
from app.core.security import create_access_token

async def refresh_token_middleware(request: Request, call_next):
    """
    Middleware that checks for expired access tokens and refreshes them
    using a valid refresh token transparently.
    """
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    new_access_token = None
    
    # Check if access token needs refresh
    should_refresh = False
    
    if access_token:
        try:
            jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"leeway": 10})
        except jwt.ExpiredSignatureError:
            should_refresh = True
        except jwt.PyJWTError:
            # Invalid token structure, try refresh anyway if present
            should_refresh = True
    elif refresh_token:
        # No access token but refresh token exists (e.g. session expired or cleared)
        should_refresh = True

    if should_refresh and refresh_token:
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if payload.get("type") == "refresh":
                email = payload.get("sub")
                new_access_token = create_access_token(
                    data={"sub": email}, 
                    expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                )
                if not hasattr(request, "_cookies"):
                    _ = request.cookies
                request._cookies["access_token"] = new_access_token
        except jwt.PyJWTError:
            pass # Invalid refresh token, do nothing (user will get 401)

    response = await call_next(request)

    # Set new cookie if refreshed
    if new_access_token:
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=True
        )

    return response

class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Получаем токен из куки или генерируем новый
        csrf_token = request.cookies.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_hex(32)
            force_set_cookie = True
        else:
            force_set_cookie = False

        # 2. Сохраняем в state, чтобы было доступно в шаблонах
        request.state.csrf_token = csrf_token

        response = await call_next(request)

        # 4. Устанавливаем куку, если её не было
        if force_set_cookie:
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                httponly=False, # Должно быть False, чтобы JS мог прочитать (если нужно), но мы передаем через шаблон
                samesite="lax",
                secure=False # True для HTTPS
            )

        return response
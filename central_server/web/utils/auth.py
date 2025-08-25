#!/usr/bin/env python3
"""
Утилиты для авторизации
"""

import os
from typing import Optional
from fastapi import HTTPException, Header


SECRET_TOKEN = os.getenv("SECRET_TOKEN", "your-secret-token-here")


async def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """Проверка токена авторизации"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:]  # Убираем "Bearer "
    
    if token != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return token

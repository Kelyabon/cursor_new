#!/usr/bin/env python3
"""
Обработчики для страницы управления ключами VPN серверов
"""

import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from db.models import ServerTask, VpnServer
from db.database import get_db
from web.utils.auth import verify_token

# Настройка шаблонов
templates = Jinja2Templates(directory="web/templates")


async def keys_page(request: Request):
    """
    Отображение страницы управления ключами
    """
    return templates.TemplateResponse("keys.html", {"request": request})


async def get_servers_list(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    API эндпоинт для получения списка активных серверов
    """
    try:
        result = await db.execute(
            select(VpnServer)
            .where(VpnServer.is_active == True)
            .order_by(desc(VpnServer.last_heartbeat_at))
        )
        servers = result.scalars().all()
        
        servers_list = []
        for server in servers:
            # Проверка онлайн статуса
            is_online = False
            if server.last_heartbeat_at:
                time_diff = datetime.now(timezone.utc) - server.last_heartbeat_at
                is_online = time_diff.total_seconds() < 300  # 5 минут
            
            servers_list.append({
                "server_id": server.server_id,
                "name": server.name or server.server_id,
                "is_online": is_online,
                "last_heartbeat_at": server.last_heartbeat_at.isoformat() if server.last_heartbeat_at else None
            })
        
        return {"servers": servers_list}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching servers: {str(e)}")


async def add_key(
    server_id: str = Form(...),
    user_email: str = Form(...),
    custom_key_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Добавление ключа на VPN сервер
    """
    try:
        # Проверка существования сервера
        server_result = await db.execute(select(VpnServer).where(VpnServer.server_id == server_id))
        server = server_result.scalar_one_or_none()
        
        if not server:
            raise HTTPException(status_code=404, detail="Сервер не найден")
        
        if not server.is_active:
            raise HTTPException(status_code=400, detail="Сервер неактивен")
        
        # Генерация ключа, если не предоставлен
        key_id = custom_key_id.strip() if custom_key_id and custom_key_id.strip() else str(uuid.uuid4())
        
        # Валидация UUID формата
        try:
            uuid.UUID(key_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат ключа (должен быть UUID)")
        
        # Проверка уникальности задачи
        existing_task = await db.execute(
            select(ServerTask).where(
                ServerTask.server_id == server_id,
                ServerTask.key_id == key_id,
                ServerTask.type == "add_key",
                ServerTask.status.in_(["pending", "delivered"])
            )
        )
        
        if existing_task.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Задача на добавление этого ключа уже существует")
        
        # Создание задачи
        task = ServerTask(
            server_id=server_id,
            type="add_key",
            key_id=key_id,
            email=user_email.strip(),
            status="pending"
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        return JSONResponse({
            "success": True,
            "message": "Задача на добавление ключа создана",
            "task_id": task.id,
            "key_id": key_id,
            "server_id": server_id,
            "user_email": user_email
        })
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании задачи: {str(e)}")


async def remove_key(
    server_id: str = Form(...),
    key_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Удаление ключа с VPN сервера
    """
    try:
        # Проверка существования сервера
        server_result = await db.execute(select(VpnServer).where(VpnServer.server_id == server_id))
        server = server_result.scalar_one_or_none()
        
        if not server:
            raise HTTPException(status_code=404, detail="Сервер не найден")
        
        # Валидация UUID формата
        try:
            uuid.UUID(key_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат ключа (должен быть UUID)")
        
        # Проверка уникальности задачи
        existing_task = await db.execute(
            select(ServerTask).where(
                ServerTask.server_id == server_id,
                ServerTask.key_id == key_id,
                ServerTask.type == "del_key",
                ServerTask.status.in_(["pending", "delivered"])
            )
        )
        
        if existing_task.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Задача на удаление этого ключа уже существует")
        
        # Создание задачи
        task = ServerTask(
            server_id=server_id,
            type="del_key",
            key_id=key_id,
            status="pending"
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        return JSONResponse({
            "success": True,
            "message": "Задача на удаление ключа создана",
            "task_id": task.id,
            "key_id": key_id,
            "server_id": server_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании задачи: {str(e)}")


async def get_tasks_status(
    server_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Получение статуса задач
    """
    try:
        query = select(ServerTask).order_by(desc(ServerTask.created_at)).limit(limit)
        
        if server_id:
            query = query.where(ServerTask.server_id == server_id)
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        return {
            "tasks": [task.to_dict() for task in tasks],
            "total_count": len(tasks)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении задач: {str(e)}")

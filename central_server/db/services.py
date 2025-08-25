#!/usr/bin/env python3
"""
Сервисы для работы с базой данных
"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import VpnServer


async def update_server_last_heartbeat(db: AsyncSession, server_id: str):
    """Обновление времени последнего heartbeat для сервера"""
    try:
        # Поиск существующего сервера
        result = await db.execute(select(VpnServer).where(VpnServer.server_id == server_id))
        server = result.scalar_one_or_none()
        
        if server:
            # Обновление существующего сервера
            server.last_heartbeat_at = datetime.now(timezone.utc)
            server.updated_at = datetime.now(timezone.utc)
        else:
            # Создание нового сервера
            server = VpnServer(
                server_id=server_id,
                name=f"Server {server_id}",
                is_active=True,
                last_heartbeat_at=datetime.now(timezone.utc)
            )
            db.add(server)
        
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        print(f"Error updating server heartbeat: {e}")

#!/usr/bin/env python3
"""
API обработчики для центрального сервера VPN
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case
from sqlalchemy.exc import IntegrityError

from db.models import ServerHeartbeat, VpnServer, ServerTask
from db.services import update_server_last_heartbeat
from db.database import get_db
from web.schemas import HeartbeatRequest, HeartbeatResponse, ServerStatsResponse
from web.utils.auth import verify_token
from web.utils.datetime_utils import parse_timestamp


async def root():
    """Корневой эндпоинт"""
    return {
        "message": "VPN Heartbeat Central Server",
        "version": "1.0.0",
        "status": "running"
    }


async def receive_heartbeat(
    heartbeat_data: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Эндпоинт для получения heartbeat данных от VPN серверов
    """
    try:
        # Парсинг временных меток
        try:
            generated_at = parse_timestamp(heartbeat_data.generated_at)
            ready_at = parse_timestamp(heartbeat_data.ready_at)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {e}")
        
        # Создание записи heartbeat
        heartbeat = ServerHeartbeat(
            server_id=heartbeat_data.server_id,
            generated_at=generated_at,
            ready_at=ready_at,
            iface=heartbeat_data.iface,
            ping_target=heartbeat_data.ping_target,
            uptime_s=heartbeat_data.uptime_s or 0,
            load1=heartbeat_data.load1 or "0.00",
            mem_total_mb=heartbeat_data.mem_total_mb or 0,
            mem_free_mb=heartbeat_data.mem_free_mb or 0,
            cpu_total_pct=heartbeat_data.cpu_total_pct or 0.0,
            softirq_pct=heartbeat_data.softirq_pct or 0.0,
            bw_rx_mbps=heartbeat_data.bw_rx_mbps or 0.0,
            bw_tx_mbps=heartbeat_data.bw_tx_mbps or 0.0,
            bw_total_mbps=heartbeat_data.bw_total_mbps or 0.0,
            pps_rx=heartbeat_data.pps_rx or 0,
            pps_tx=heartbeat_data.pps_tx or 0,
            pps_total=heartbeat_data.pps_total or 0,
            conn_est_rate_s=heartbeat_data.conn_est_rate_s or 0,
            active_conns=heartbeat_data.active_conns or 0,
            conntrack_usage_pct=heartbeat_data.conntrack_usage_pct or 0.0,
            rx_dropped=heartbeat_data.rx_dropped or 0,
            tx_dropped=heartbeat_data.tx_dropped or 0,
            latency_p50_ms=heartbeat_data.latency_p50_ms or 0.0,
            latency_p95_ms=heartbeat_data.latency_p95_ms or 0.0,
            packet_loss_pct=heartbeat_data.packet_loss_pct or 0.0,
        )
        
        # Сохранение в БД
        db.add(heartbeat)
        await db.commit()
        await db.refresh(heartbeat)
        
        # Обновление информации о сервере
        await update_server_last_heartbeat(db, heartbeat_data.server_id)
        
        return HeartbeatResponse(
            success=True,
            message="Heartbeat received successfully",
            heartbeat_id=heartbeat.id
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving heartbeat: {str(e)}")


async def get_servers(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Получение списка всех серверов"""
    try:
        result = await db.execute(select(VpnServer).order_by(desc(VpnServer.last_heartbeat_at)))
        servers = result.scalars().all()
        
        return [server.to_dict() for server in servers]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching servers: {str(e)}")


async def get_server_stats(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Получение статистики по конкретному серверу"""
    try:
        # Проверка существования сервера
        server_result = await db.execute(select(VpnServer).where(VpnServer.server_id == server_id))
        server = server_result.scalar_one_or_none()
        
        # Получение последнего heartbeat
        last_heartbeat_result = await db.execute(
            select(ServerHeartbeat)
            .where(ServerHeartbeat.server_id == server_id)
            .order_by(desc(ServerHeartbeat.created_at))
            .limit(1)
        )
        last_heartbeat = last_heartbeat_result.scalar_one_or_none()
        
        # Подсчет общего количества heartbeat'ов
        count_result = await db.execute(
            select(func.count(ServerHeartbeat.id))
            .where(ServerHeartbeat.server_id == server_id)
        )
        heartbeat_count = count_result.scalar() or 0
        
        # Вычисление средних значений за последние 24 часа
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        
        avg_result = await db.execute(
            select(
                func.avg(ServerHeartbeat.cpu_total_pct),
                func.avg(case(
                    (ServerHeartbeat.mem_total_mb > 0, 
                     (ServerHeartbeat.mem_total_mb - ServerHeartbeat.mem_free_mb) * 100.0 / ServerHeartbeat.mem_total_mb),
                    else_=0
                )),
                func.avg(ServerHeartbeat.latency_p50_ms)
            )
            .where(ServerHeartbeat.server_id == server_id)
            .where(ServerHeartbeat.created_at >= yesterday)
        )
        avg_stats = avg_result.first()
        
        return ServerStatsResponse(
            server_id=server_id,
            is_registered=server is not None,
            last_heartbeat=last_heartbeat.to_dict() if last_heartbeat else None,
            heartbeat_count=heartbeat_count,
            avg_cpu_pct=round(avg_stats[0], 2) if avg_stats[0] else None,
            avg_mem_usage_pct=round(avg_stats[1], 2) if avg_stats[1] else None,
            avg_latency_ms=round(avg_stats[2], 2) if avg_stats[2] else None,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching server stats: {str(e)}")


async def get_server_heartbeats(
    server_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Получение heartbeat'ов для конкретного сервера"""
    try:
        result = await db.execute(
            select(ServerHeartbeat)
            .where(ServerHeartbeat.server_id == server_id)
            .order_by(desc(ServerHeartbeat.created_at))
            .limit(limit)
            .offset(offset)
        )
        heartbeats = result.scalars().all()
        
        return {
            "server_id": server_id,
            "heartbeats": [hb.to_dict() for hb in heartbeats],
            "count": len(heartbeats),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching heartbeats: {str(e)}")


async def get_tasks(
    server_id: Optional[str] = None,
    token: str = Depends(verify_token)
):
    """Возврат задач для агента. Если server_id не задан, вернуть пусто."""
    if not server_id:
        return []
    # В реальной системе здесь стоит добавить аутентификацию сервера и маркеры доставки
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ServerTask).where(ServerTask.server_id == server_id, ServerTask.status == "pending").order_by(ServerTask.id.asc())
        )
        tasks = result.scalars().all()
        # Пометим как delivered (мягкая доставка), агент после применения может стукнуть отдельный ack
        for t in tasks:
            t.status = "delivered"
        await db.commit()
        return [
            {
                "type": t.type,
                "id": t.key_id,
                "email": t.email,
                "payload": t.payload,
                "task_id": t.id,
            }
            for t in tasks
        ]


async def ack_task(
    task_id: int,
    status: str,
    token: str = Depends(verify_token)
):
    """Агент подтверждает выполнение задачи (done/failed)."""
    status = status.lower()
    if status not in ("done", "failed"):
        raise HTTPException(status_code=400, detail="invalid status")
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ServerTask).where(ServerTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        task.status = status
        await db.commit()
        return {"ok": True}


async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик ошибок"""
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

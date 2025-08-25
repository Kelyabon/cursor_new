#!/usr/bin/env python3
"""
Обработчики для страницы статистики с графиками
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from fastapi import HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case, and_

from db.models import ServerHeartbeat, VpnServer
from db.database import get_db
from web.utils.auth import verify_token

# Настройка шаблонов
templates = Jinja2Templates(directory="web/templates")


async def stats_page(request: Request):
    """
    Отображение страницы статистики с графиками
    """
    return templates.TemplateResponse("stats.html", {"request": request})


async def get_stats_data(
    hours: int = 24,
    server_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    API эндпоинт для получения данных статистики для графиков
    """
    try:
        # Временной диапазон
        time_limit = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Базовый запрос
        query = select(ServerHeartbeat).where(ServerHeartbeat.created_at >= time_limit)
        
        # Фильтр по серверу, если указан
        if server_id:
            query = query.where(ServerHeartbeat.server_id == server_id)
        
        # Сортировка по времени
        query = query.order_by(ServerHeartbeat.created_at)
        
        # Выполнение запроса
        result = await db.execute(query)
        heartbeats = result.scalars().all()
        
        # Группировка данных по серверам
        servers_data = {}
        timeline = []
        
        for hb in heartbeats:
            if hb.server_id not in servers_data:
                servers_data[hb.server_id] = {
                    'server_id': hb.server_id,
                    'cpu_data': [],
                    'memory_data': [],
                    'bandwidth_rx_data': [],
                    'bandwidth_tx_data': [],
                    'latency_p50_data': [],
                    'latency_p95_data': [],
                    'packet_loss_data': [],
                    'active_conns_data': [],
                    'timestamps': []
                }
            
            # Вычисление использования памяти в процентах
            memory_usage_pct = 0
            if hb.mem_total_mb > 0:
                memory_usage_pct = ((hb.mem_total_mb - hb.mem_free_mb) * 100.0) / hb.mem_total_mb
            
            # Добавление данных
            timestamp = hb.created_at.isoformat()
            servers_data[hb.server_id]['timestamps'].append(timestamp)
            servers_data[hb.server_id]['cpu_data'].append(hb.cpu_total_pct)
            servers_data[hb.server_id]['memory_data'].append(round(memory_usage_pct, 2))
            servers_data[hb.server_id]['bandwidth_rx_data'].append(hb.bw_rx_mbps)
            servers_data[hb.server_id]['bandwidth_tx_data'].append(hb.bw_tx_mbps)
            servers_data[hb.server_id]['latency_p50_data'].append(hb.latency_p50_ms)
            servers_data[hb.server_id]['latency_p95_data'].append(hb.latency_p95_ms)
            servers_data[hb.server_id]['packet_loss_data'].append(hb.packet_loss_pct)
            servers_data[hb.server_id]['active_conns_data'].append(hb.active_conns)
            
            # Добавляем временную метку в общий timeline
            if timestamp not in timeline:
                timeline.append(timestamp)
        
        # Получение информации о серверах
        servers_query = select(VpnServer)
        if server_id:
            servers_query = servers_query.where(VpnServer.server_id == server_id)
        
        servers_result = await db.execute(servers_query)
        servers_info = {s.server_id: s.to_dict() for s in servers_result.scalars().all()}
        
        # Сортировка timeline
        timeline.sort()
        
        return {
            "servers_data": list(servers_data.values()),
            "servers_info": servers_info,
            "timeline": timeline,
            "total_servers": len(servers_data),
            "time_range_hours": hours,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats data: {str(e)}")


async def get_current_stats(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Получение текущей статистики всех серверов (последние значения)
    """
    try:
        # Получаем последний heartbeat для каждого сервера
        # Используем оконную функцию для получения последней записи по каждому серверу
        subquery = select(
            ServerHeartbeat,
            func.row_number().over(
                partition_by=ServerHeartbeat.server_id,
                order_by=desc(ServerHeartbeat.created_at)
            ).label('rn')
        ).subquery()
        
        # Выбираем только первые записи (rn = 1)
        query = select(subquery).where(subquery.c.rn == 1)
        
        result = await db.execute(query)
        latest_heartbeats = result.all()
        
        current_stats = []
        for row in latest_heartbeats:
            # Вычисление использования памяти
            memory_usage_pct = 0
            if row.mem_total_mb > 0:
                memory_usage_pct = ((row.mem_total_mb - row.mem_free_mb) * 100.0) / row.mem_total_mb
            
            # Определение статуса сервера
            time_diff = datetime.now(timezone.utc) - row.created_at
            is_online = time_diff.total_seconds() < 300  # 5 минут
            
            current_stats.append({
                "server_id": row.server_id,
                "is_online": is_online,
                "last_update": row.created_at.isoformat(),
                "cpu_usage_pct": row.cpu_total_pct,
                "memory_usage_pct": round(memory_usage_pct, 2),
                "memory_total_mb": row.mem_total_mb,
                "memory_free_mb": row.mem_free_mb,
                "bandwidth_rx_mbps": row.bw_rx_mbps,
                "bandwidth_tx_mbps": row.bw_tx_mbps,
                "bandwidth_total_mbps": row.bw_total_mbps,
                "latency_p50_ms": row.latency_p50_ms,
                "latency_p95_ms": row.latency_p95_ms,
                "packet_loss_pct": row.packet_loss_pct,
                "active_connections": row.active_conns,
                "uptime_hours": round(row.uptime_s / 3600, 1),
                "load_avg": row.load1
            })
        
        return {
            "current_stats": current_stats,
            "total_servers": len(current_stats),
            "online_servers": sum(1 for s in current_stats if s["is_online"]),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching current stats: {str(e)}")


async def get_server_list(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Получение списка серверов для выпадающего меню
    """
    try:
        result = await db.execute(
            select(VpnServer.server_id, VpnServer.name, VpnServer.is_active, VpnServer.last_heartbeat_at)
            .order_by(desc(VpnServer.last_heartbeat_at))
        )
        servers = result.all()
        
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
                "is_active": server.is_active,
                "is_online": is_online,
                "last_heartbeat_at": server.last_heartbeat_at.isoformat() if server.last_heartbeat_at else None
            })
        
        return {
            "servers": servers_list,
            "total_count": len(servers_list)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching server list: {str(e)}")

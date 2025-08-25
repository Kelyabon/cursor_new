#!/usr/bin/env python3
"""
Центральный сервер для сбора heartbeat данных от VPN серверов
"""

import os
from central_server.web.utils import keys
import uvicorn
from contextlib import asynccontextmanager
from typing import List, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from db.database import lifespan_manager
from web.handlers import api, stats
from web.schemas import HeartbeatResponse, ServerStatsResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    async with lifespan_manager():
        yield


# Создание FastAPI приложения
app = FastAPI(
    title="VPN Heartbeat Central Server",
    description="Центральный сервер для сбора статистики от VPN серверов",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация API эндпоинтов
app.get("/", response_model=Dict[str, str])(api.root)
app.post("/heartbeat", response_model=HeartbeatResponse)(api.receive_heartbeat)
app.get("/servers", response_model=List[Dict[str, Any]])(api.get_servers)
app.get("/servers/{server_id}/stats", response_model=ServerStatsResponse)(api.get_server_stats)
app.get("/servers/{server_id}/heartbeats")(api.get_server_heartbeats)
app.get("/tasks")(api.get_tasks)
app.post("/tasks/{task_id}/ack")(api.ack_task)

# Регистрация эндпоинтов статистики
app.get("/stats", response_class=HTMLResponse)(stats.stats_page)
app.get("/api/stats/data")(stats.get_stats_data)
app.get("/api/stats/current")(stats.get_current_stats)
app.get("/api/stats/servers")(stats.get_server_list)

# Регистрация эндпоинтов управления ключами
app.get("/keys", response_class=HTMLResponse)(keys.keys_page)
app.get("/api/keys/servers")(keys.get_servers_list)
app.post("/api/keys/add")(keys.add_key)
app.post("/api/keys/remove")(keys.remove_key)
app.get("/api/keys/tasks")(keys.get_tasks_status)

# Регистрация обработчика ошибок
app.exception_handler(Exception)(api.global_exception_handler)


if __name__ == "__main__":
    # Конфигурация из переменных окружения
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    print(f"Запуск сервера на {host}:{port}")
    print(f"DEBUG режим: {debug}")
    print(f"База данных: {os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./heartbeat.db')}")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=debug,
        access_log=True,
        log_level="info" if not debug else "debug"
    )
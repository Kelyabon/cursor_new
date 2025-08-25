#!/usr/bin/env python3
"""
Pydantic модели для API
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class HeartbeatRequest(BaseModel):
    """Модель для входящих heartbeat данных"""
    server_id: str = Field(..., min_length=1, max_length=255)
    generated_at: str = Field(..., description="ISO timestamp когда данные были сгенерированы")
    ready_at: str = Field(..., description="ISO timestamp когда данные готовы к отправке")
    
    # Опциональные поля
    iface: Optional[str] = Field(None, max_length=100)
    ping_target: Optional[str] = Field(None, max_length=100)
    
    # Системная информация
    uptime_s: Optional[int] = Field(0, ge=0)
    load1: Optional[str] = Field("0.00", max_length=10)
    mem_total_mb: Optional[int] = Field(0, ge=0)
    mem_free_mb: Optional[int] = Field(0, ge=0)
    
    # CPU статистика
    cpu_total_pct: Optional[float] = Field(0.0, ge=0.0, le=100.0)
    softirq_pct: Optional[float] = Field(0.0, ge=0.0, le=100.0)
    
    # Пропускная способность
    bw_rx_mbps: Optional[float] = Field(0.0, ge=0.0)
    bw_tx_mbps: Optional[float] = Field(0.0, ge=0.0)
    bw_total_mbps: Optional[float] = Field(0.0, ge=0.0)
    
    # Пакеты в секунду
    pps_rx: Optional[int] = Field(0, ge=0)
    pps_tx: Optional[int] = Field(0, ge=0)
    pps_total: Optional[int] = Field(0, ge=0)
    
    # Соединения
    conn_est_rate_s: Optional[int] = Field(0, ge=0)
    active_conns: Optional[int] = Field(0, ge=0)
    conntrack_usage_pct: Optional[float] = Field(0.0, ge=0.0, le=100.0)
    
    # Ошибки
    rx_dropped: Optional[int] = Field(0, ge=0)
    tx_dropped: Optional[int] = Field(0, ge=0)
    
    # Латентность
    latency_p50_ms: Optional[float] = Field(0.0, ge=0.0)
    latency_p95_ms: Optional[float] = Field(0.0, ge=0.0)
    packet_loss_pct: Optional[float] = Field(0.0, ge=0.0, le=100.0)


class HeartbeatResponse(BaseModel):
    """Ответ на heartbeat запрос"""
    success: bool
    message: str
    heartbeat_id: Optional[int] = None


class ServerStatsResponse(BaseModel):
    """Статистика по серверу"""
    server_id: str
    is_registered: bool
    last_heartbeat: Optional[Dict[str, Any]] = None
    heartbeat_count: int
    avg_cpu_pct: Optional[float] = None
    avg_mem_usage_pct: Optional[float] = None
    avg_latency_ms: Optional[float] = None

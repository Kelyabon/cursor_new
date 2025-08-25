#!/usr/bin/env python3
"""
SQLAlchemy 2.0 async модели для центрального сервера VPN
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.sqlite import JSON as SqliteJSON


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass


class ServerHeartbeat(Base):
    """Модель для хранения heartbeat данных от VPN серверов"""
    
    __tablename__ = "server_heartbeats"
    
    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Временные метки
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # Сетевая информация
    iface: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ping_target: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Системная информация
    uptime_s: Mapped[int] = mapped_column(Integer, default=0)
    load1: Mapped[str] = mapped_column(String(10), default="0.00")
    mem_total_mb: Mapped[int] = mapped_column(Integer, default=0)
    mem_free_mb: Mapped[int] = mapped_column(Integer, default=0)
    
    # CPU статистика
    cpu_total_pct: Mapped[float] = mapped_column(Float, default=0.0)
    softirq_pct: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Пропускная способность (Мбит/с)
    bw_rx_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    bw_tx_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    bw_total_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Пакеты в секунду
    pps_rx: Mapped[int] = mapped_column(Integer, default=0)
    pps_tx: Mapped[int] = mapped_column(Integer, default=0)
    pps_total: Mapped[int] = mapped_column(Integer, default=0)
    
    # Соединения
    conn_est_rate_s: Mapped[int] = mapped_column(Integer, default=0)
    active_conns: Mapped[int] = mapped_column(Integer, default=0)
    conntrack_usage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Ошибки и потери
    rx_dropped: Mapped[int] = mapped_column(Integer, default=0)
    tx_dropped: Mapped[int] = mapped_column(Integer, default=0)
    
    # Латентность и потери пакетов
    latency_p50_ms: Mapped[float] = mapped_column(Float, default=0.0)
    latency_p95_ms: Mapped[float] = mapped_column(Float, default=0.0)
    packet_loss_pct: Mapped[float] = mapped_column(Float, default=0.0)
    
    def __repr__(self) -> str:
        return f"<ServerHeartbeat(id={self.id}, server_id='{self.server_id}', generated_at='{self.generated_at}')>"
    
    def to_dict(self) -> dict:
        """Преобразование модели в словарь для JSON сериализации"""
        return {
            "id": self.id,
            "server_id": self.server_id,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "ready_at": self.ready_at.isoformat() if self.ready_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "iface": self.iface,
            "ping_target": self.ping_target,
            "uptime_s": self.uptime_s,
            "load1": self.load1,
            "mem_total_mb": self.mem_total_mb,
            "mem_free_mb": self.mem_free_mb,
            "cpu_total_pct": self.cpu_total_pct,
            "softirq_pct": self.softirq_pct,
            "bw_rx_mbps": self.bw_rx_mbps,
            "bw_tx_mbps": self.bw_tx_mbps,
            "bw_total_mbps": self.bw_total_mbps,
            "pps_rx": self.pps_rx,
            "pps_tx": self.pps_tx,
            "pps_total": self.pps_total,
            "conn_est_rate_s": self.conn_est_rate_s,
            "active_conns": self.active_conns,
            "conntrack_usage_pct": self.conntrack_usage_pct,
            "rx_dropped": self.rx_dropped,
            "tx_dropped": self.tx_dropped,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "packet_loss_pct": self.packet_loss_pct,
        }


class VpnServer(Base):
    """Модель для регистрации VPN серверов"""
    
    __tablename__ = "vpn_servers"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Статус сервера
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<VpnServer(id={self.id}, server_id='{self.server_id}', is_active={self.is_active})>"
    
    def to_dict(self) -> dict:
        """Преобразование модели в словарь для JSON сериализации"""
        return {
            "id": self.id,
            "server_id": self.server_id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ServerTask(Base):
    """Очередь задач для VPN серверов (центральный сервер -> агент)"""

    __tablename__ = "server_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # add_key | del_key | custom
    key_id: Mapped[str] = mapped_column(String(255), nullable=False)  # соответствует id пользователя (UUID)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(SqliteJSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | delivered | done | failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "server_id": self.server_id,
            "type": self.type,
            "key_id": self.key_id,
            "email": self.email,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

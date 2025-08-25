#!/usr/bin/env python3
"""
Конфигурация и управление подключением к базе данных
"""

import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from db.models import Base


# Конфигурация базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./heartbeat.db")

# Создание async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Установить True для отладки SQL запросов
    pool_pre_ping=True,
)

# Создание async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Dependency для получения сессии БД
async def get_db() -> AsyncSession:
    """Получение асинхронной сессии базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def lifespan_manager():
    """Управление жизненным циклом подключения к БД"""
    # Startup
    await init_db()
    print("База данных инициализирована")
    yield
    # Shutdown
    await engine.dispose()
    print("Соединения с базой данных закрыты")

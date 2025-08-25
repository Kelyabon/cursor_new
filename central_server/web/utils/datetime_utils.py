#!/usr/bin/env python3
"""
Утилиты для работы с датой и временем
"""

from datetime import datetime


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Парсинг ISO timestamp строки в datetime объект
    
    Args:
        timestamp_str: ISO timestamp строка (поддерживает Z суффикс)
    
    Returns:
        datetime: Распарсенный datetime объект
    
    Raises:
        ValueError: Если формат timestamp неверный
    """
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

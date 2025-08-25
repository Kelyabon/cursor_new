# VPN Heartbeat Central Server

Центральный сервер для сбора и хранения статистики от VPN серверов.

## Описание

Этот сервер принимает heartbeat данные от VPN агентов и сохраняет их в базе данных для мониторинга и анализа.

## Установка и запуск

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка конфигурации

Скопируйте `config_example.env` в `.env` и настройте:

```bash
cp config_example.env .env
```

Отредактируйте файл `.env`:
- `SECRET_TOKEN` - токен для авторизации агентов
- `DATABASE_URL` - строка подключения к БД
- `HOST`, `PORT` - хост и порт для сервера

### 3. Запуск сервера

```bash
python run.py
```

Или через uvicorn напрямую:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## API Эндпоинты

### Основные эндпоинты

- `POST /heartbeat` - Прием heartbeat данных от агентов
- `GET /servers` - Список всех серверов
- `GET /servers/{server_id}/stats` - Статистика по серверу
- `GET /servers/{server_id}/heartbeats` - История heartbeat'ов сервера

### Авторизация

Все эндпоинты (кроме корневого) требуют авторизацию через Bearer token:

```
Authorization: Bearer your-secret-token-here
```

### Пример heartbeat запроса

```json
{
  "server_id": "server-001",
  "generated_at": "2024-01-15T10:30:00Z",
  "ready_at": "2024-01-15T10:30:01Z",
  "iface": "eth0",
  "ping_target": "1.1.1.1",
  "uptime_s": 86400,
  "load1": "0.75",
  "mem_total_mb": 2048,
  "mem_free_mb": 1024,
  "cpu_total_pct": 25.5,
  "softirq_pct": 5.2,
  "bw_rx_mbps": 100.5,
  "bw_tx_mbps": 50.2,
  "bw_total_mbps": 150.7,
  "pps_rx": 1500,
  "pps_tx": 800,
  "pps_total": 2300,
  "conn_est_rate_s": 50,
  "active_conns": 1200,
  "conntrack_usage_pct": 15.5,
  "rx_dropped": 0,
  "tx_dropped": 0,
  "latency_p50_ms": 25.5,
  "latency_p95_ms": 45.2,
  "packet_loss_pct": 0.1
}
```

## Структура проекта

```
central_server/
├── app.py              # Основное FastAPI приложение
├── models.py           # SQLAlchemy модели
├── requirements.txt    # Зависимости Python
├── run.py             # Скрипт запуска
├── config_example.env # Пример конфигурации
└── README.md          # Документация
```

## База данных

По умолчанию используется SQLite. Для production рекомендуется PostgreSQL.

### Таблицы

- `server_heartbeats` - Хранение heartbeat данных
- `vpn_servers` - Регистрация серверов

## Мониторинг

Сервер автоматически регистрирует новые серверы при получении первого heartbeat'а и отслеживает время последнего обновления.

## Переменные окружения

- `DATABASE_URL` - URL подключения к БД
- `SECRET_TOKEN` - Токен авторизации
- `HOST` - Хост для привязки (по умолчанию 0.0.0.0)
- `PORT` - Порт (по умолчанию 8000)
- `DEBUG` - Режим отладки (true/false)

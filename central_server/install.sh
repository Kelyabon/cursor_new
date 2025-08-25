#!/bin/bash

# VPN Heartbeat Central Server Installation Script

set -e

echo "=== VPN Heartbeat Central Server Installation ==="

# Проверка Python 3.8+
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
            echo "✓ Python 3.$PYTHON_MINOR найден"
            PYTHON_CMD="python3"
        else
            echo "✗ Требуется Python 3.8 или выше. Найден: $PYTHON_VERSION"
            exit 1
        fi
    else
        echo "✗ Python 3 не найден. Установите Python 3.8 или выше"
        exit 1
    fi
}

# Создание виртуального окружения
setup_venv() {
    echo "Создание виртуального окружения..."
    if [ ! -d "venv" ]; then
        $PYTHON_CMD -m venv venv
        echo "✓ Виртуальное окружение создано"
    else
        echo "✓ Виртуальное окружение уже существует"
    fi
    
    # Активация виртуального окружения
    source venv/bin/activate
    echo "✓ Виртуальное окружение активировано"
}

# Обновление pip
update_pip() {
    echo "Обновление pip..."
    pip install --upgrade pip
    echo "✓ pip обновлен"
}

# Установка зависимостей
install_dependencies() {
    echo "Установка зависимостей из requirements.txt..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        echo "✓ Зависимости установлены"
    else
        echo "✗ Файл requirements.txt не найден"
        exit 1
    fi
}

# Настройка конфигурации
setup_config() {
    echo "Настройка конфигурации..."
    
    if [ ! -f ".env" ]; then
        if [ -f "config_example.env" ]; then
            cp config_example.env .env
            echo "✓ Конфигурационный файл .env создан из config_example.env"
            echo "⚠ Отредактируйте файл .env для настройки:"
            echo "  - SECRET_TOKEN - токен для авторизации агентов"
            echo "  - DATABASE_URL - строка подключения к БД"
            echo "  - HOST, PORT - хост и порт для сервера"
        else
            # Создание базового .env файла
            cat > .env << EOF
# Центральный сервер VPN - конфигурация
SECRET_TOKEN=your-secret-token-here
DATABASE_URL=sqlite+aiosqlite:///./heartbeat.db
HOST=0.0.0.0
PORT=8000
DEBUG=false
EOF
            echo "✓ Базовый конфигурационный файл .env создан"
            echo "⚠ Обязательно измените SECRET_TOKEN в файле .env!"
        fi
    else
        echo "✓ Конфигурационный файл .env уже существует"
    fi
}

# Инициализация базы данных
init_database() {
    echo "Инициализация базы данных..."
    # База данных инициализируется автоматически при первом запуске
    echo "✓ База данных будет инициализирована при первом запуске"
}

# Создание скрипта запуска
create_start_script() {
    echo "Создание скрипта запуска..."
    cat > start.sh << 'EOF'
#!/bin/bash
# Скрипт запуска VPN Heartbeat Central Server

cd "$(dirname "$0")"

# Активация виртуального окружения
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Виртуальное окружение активировано"
else
    echo "✗ Виртуальное окружение не найдено. Запустите install.sh"
    exit 1
fi

# Загрузка переменных окружения
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✓ Переменные окружения загружены"
fi

# Запуск сервера
echo "Запуск VPN Heartbeat Central Server..."
python app.py
EOF
    chmod +x start.sh
    echo "✓ Скрипт запуска создан (start.sh)"
}

# Создание systemd сервиса (опционально)
create_systemd_service() {
    echo "Создание systemd сервиса..."
    CURRENT_DIR=$(pwd)
    USER=$(whoami)
    
    cat > vpn-central-server.service << EOF
[Unit]
Description=VPN Heartbeat Central Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/venv/bin
ExecStart=$CURRENT_DIR/venv/bin/python $CURRENT_DIR/app.py
EnvironmentFile=$CURRENT_DIR/.env
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    echo "✓ Systemd сервис файл создан (vpn-central-server.service)"
    echo "  Для установки сервиса:"
    echo "  sudo cp vpn-central-server.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable vpn-central-server"
    echo "  sudo systemctl start vpn-central-server"
}

# Основная установка
main() {
    echo "Начинаем установку VPN Heartbeat Central Server..."
    
    check_python
    setup_venv
    update_pip
    install_dependencies
    setup_config
    init_database
    create_start_script
    create_systemd_service
    
    echo ""
    echo "=== Установка завершена! ==="
    echo ""
    echo "Следующие шаги:"
    echo "1. Отредактируйте файл .env и установите правильный SECRET_TOKEN"
    echo "2. Запустите сервер: ./start.sh"
    echo "3. Или используйте: source venv/bin/activate && python app.py"
    echo ""
    echo "Сервер будет доступен по адресу: http://localhost:8000"
    echo "API документация: http://localhost:8000/docs"
    echo ""
    echo "Для настройки автозапуска установите systemd сервис:"
    echo "sudo cp vpn-central-server.service /etc/systemd/system/"
    echo "sudo systemctl enable vpn-central-server"
    echo ""
}

# Запуск основной функции
main

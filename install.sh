#!/bin/bash

set -e

# Конфигурация
INSTALL_DIR="/opt/avavavpn-bot"
PROJECT_NAME="avavavpn-bot"
CONFIG_FILE="$INSTALL_DIR/.env"
REPO_URL="https://github.com/ADSFAL-US/avavavpn-bot.git"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Проверка зависимостей
check_dependencies() {
    log_info "Проверка зависимостей..."
    
    local missing_deps=()
    
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    else
        log_success "Docker: $(docker --version)"
    fi
    
    if ! docker compose version &> /dev/null 2>&1 && ! command -v docker-compose &> /dev/null; then
        missing_deps+=("docker-compose")
    else
        log_success "Docker Compose: OK"
    fi
    
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
    else
        log_success "Git: $(git --version)"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Отсутствуют: ${missing_deps[*]}"
        echo "  sudo apt update && sudo apt install -y docker.io docker-compose-plugin git"
        exit 1
    fi
}

# Проверка root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Требуется root (sudo)"
        exit 1
    fi
}

# Установка
install_new() {
    log_info "Новая установка в $INSTALL_DIR"
    
    # Клонируем репозиторий
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Репозиторий уже существует, обновляем..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        log_info "Клонирование репозитория..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    
    cd "$INSTALL_DIR"
    
    # Запрашиваем конфигурацию
    echo ""
    log_info "Настройка Telegram бота"
    echo ""
    
    read -p "Enter Bot Token (from @BotFather): " bot_token
    while [ -z "$bot_token" ]; do
        log_error "Bot Token обязателен!"
        read -p "Enter Bot Token: " bot_token
    done
    
    read -p "Enter Admin IDs (comma-separated Telegram IDs): " admin_ids
    admin_ids=${admin_ids:-"0"}
    
    # Опциональные настройки x-controller интеграции
    echo ""
    log_info "Интеграция с x-controller (опционально)"
    echo ""
    
    read -p "X-Controller URL [http://localhost:8080]: " controller_url
    controller_url=${controller_url:-"http://localhost:8080"}
    
    read -p "X-Controller API Key (если настроен): " api_key
    
    # Создаем .env
    cat > "$INSTALL_DIR/.env" << EOF
# Telegram Bot Configuration
BOT_TOKEN=$bot_token
ADMIN_IDS=$admin_ids

# Database
DATABASE_PATH=/app/data/avava_vpn.db

# X-Controller Integration
XCONTROLLER_URL=$controller_url
XCONTROLLER_API_KEY=${api_key:-}

# Bot Settings
SUPPORT_USERNAME=@support
DEFAULT_TRIAL_DAYS=3
EOF
    log_success ".env создан"
    
    # Создаем директорию для данных
    mkdir -p "$INSTALL_DIR/data"
    
    log_info "Сборка..."
    docker compose build --no-cache
    
    log_info "Запуск..."
    docker compose up -d
    
    log_success "Бот запущен!"
    log_info "Проверьте статус: docker compose logs -f"
    log_info "Остановка: docker compose down"
    log_info "Перезапуск: docker compose restart"
}

# Обновление
update_existing() {
    log_info "Обновление существующей установки"
    
    cd "$INSTALL_DIR"
    
    log_info "Остановка..."
    docker compose down
    
    # Обновляем из репозитория
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Обновление из репозитория..."
        git pull origin main
    else
        log_warning "Не найден git репозиторий, пропускаем обновление кода"
    fi
    
    log_info "Пересборка..."
    docker compose build --no-cache
    
    log_info "Запуск..."
    docker compose up -d
    
    docker image prune -f
    
    log_success "Обновлено!"
}

# Главная функция
main() {
    echo "========================================"
    echo "  AvavaVPN Bot Installer"
    echo "========================================"
    
    check_root
    check_dependencies
    
    if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR")" ]; then
        read -p "Установка уже существует. Обновить? [Y/n]: " confirm
        if [[ $confirm =~ ^[Nn]$ ]]; then
            log_info "Отменено"
            exit 0
        fi
        update_existing
    else
        install_new
    fi
    
    echo "========================================"
    log_success "Готово!"
    echo "========================================"
}

main "$@"

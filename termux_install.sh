#!/usr/bin/env bash
#
# Установка зависимостей для запуска приложения в Termux на Android.
# Скрипт устанавливает системные пакеты, создаёт виртуальное окружение
# и ставит Python-зависимости из requirements.txt.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]]; then
  echo "⚠️ Похоже, что вы запускаете скрипт вне Termux (PREFIX=${PREFIX:-unset})."
  echo "Скрипт предназначен для среды Termux, продолжение — на ваш страх и риск."
fi

echo "==> Обновление пакетов Termux..."
pkg update -y
pkg upgrade -y

echo "==> Установка системных зависимостей..."
pkg install -y python git libffi openssl

echo "==> Создание виртуального окружения (.venv)..."
cd "$REPO_ROOT"
if [[ ! -d .venv ]]; then
  python -m venv .venv
fi

source .venv/bin/activate

echo "==> Обновление pip..."
pip install --upgrade pip

echo "==> Установка Python-зависимостей..."
pip install -r requirements.txt

cat <<'EOF'
Готово.

1) Создайте файл .env в корне репозитория и заполните:
   API_ID=ваш_api_id
   API_HASH=ваш_api_hash
   SESSION_NAME=опциональное_имя_сессии
   NTP_HOST=pool.ntp.org   # опционально

2) Запустите приложение:
   source .venv/bin/activate
   python main.py
EOF

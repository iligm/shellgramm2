#!/usr/bin/env bash
#
# Установка зависимостей для запуска приложения в Termux на Android.
# Скрипт можно запускать напрямую через curl, он сам скачает репозиторий,
# установит системные пакеты и Python-зависимости.

set -euo pipefail

DEFAULT_REPO_URL="https://github.com/iligm/shellgramm2.git"
REPO_URL="${REPO_URL:-$DEFAULT_REPO_URL}"
BRANCH="${BRANCH:-main}"
REPO_DIR="${REPO_DIR:-"$HOME/shellgramm2"}"

# Если скрипт запущен в уже клонированном репозитории, работаем в нём,
# иначе используем REPO_DIR.
if git -C "$PWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "$PWD" rev-parse --show-toplevel)"
else
  REPO_ROOT="$REPO_DIR"
fi

if [[ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]]; then
  echo "⚠️ Похоже, что вы запускаете скрипт вне Termux (PREFIX=${PREFIX:-unset})."
  echo "Скрипт предназначен для среды Termux, продолжение — на ваш страх и риск."
fi

echo "==> Обновление пакетов Termux..."
pkg update -y
pkg upgrade -y

echo "==> Установка системных зависимостей..."
pkg install -y python git libffi openssl clang

echo "==> Загрузка или обновление репозитория..."
if [[ -d "$REPO_ROOT/.git" ]]; then
  echo "   Найден существующий репозиторий: $REPO_ROOT"
  git -C "$REPO_ROOT" fetch --depth=1 origin "$BRANCH" || true
  git -C "$REPO_ROOT" checkout "$BRANCH" || true
  git -C "$REPO_ROOT" pull --ff-only origin "$BRANCH" || true
else
  rm -rf "$REPO_ROOT"
  git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$REPO_ROOT"
fi

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

if [[ ! -f .env ]]; then
  echo "==> Создание файла .env..."
  python3 <<'PYTHON_SCRIPT'
import os

env_path = ".env"

print("Файл .env не найден. Пожалуйста, введите настройки в следующем формате:")
print("API_ID=aaaaaaa")
print("API_HASH=aaaaaaa")
print("SESSION_NAME=userbot_session")
print("NTP_HOST=pool.ntp.org")
print("\nВведите данные (можно вставить все строки сразу, завершите ввод пустой строкой):")

lines = []
while True:
    try:
        line = input()
        if not line.strip():
            break
        lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print("\nВвод прерван.")
        exit(1)

if not lines:
    print("Ошибка: Не введены данные для .env файла.")
    exit(1)

# Сохраняем введенные данные в .env файл
with open(env_path, "w", encoding="utf-8") as f:
    for line in lines:
        f.write(line + "\n")

print("Файл .env создан.")
PYTHON_SCRIPT
fi

cat <<'EOF'
Готово.

Запустите приложение:
   source .venv/bin/activate
   python main.py

Подсказки:
- Можно указать REPO_URL, BRANCH или REPO_DIR перед запуском скрипта,
  чтобы задать свой форк/ветку или путь установки.
- Пример curl-запуска:
    curl -fsSL https://raw.githubusercontent.com/shellgramm/shellgramm2/main/termux_install.sh | bash
EOF

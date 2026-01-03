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
  echo "Похоже, что вы запускаете скрипт вне Termux (PREFIX=${PREFIX:-unset})."
  echo "Скрипт предназначен для среды Termux, продолжение — на ваш страх и риск."
fi

# Важно: при запуске через `curl ... | bash` stdin не интерактивный.
# Поэтому подавляем любые вопросы dpkg и ВСЕГДА берём конфиги мейнтейнера.
export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(
  -y
  -o Dpkg::Options::=--force-confdef
  -o Dpkg::Options::=--force-confnew
)

echo "==> Обновление индекса пакетов Termux..."
apt-get update

echo "==> Обновление установленных пакетов (конфиги = версия мейнтейнера)..."
apt-get "${APT_OPTS[@]}" upgrade --with-new-pkgs

echo "==> Установка системных зависимостей..."
apt-get "${APT_OPTS[@]}" install python git libffi openssl clang

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

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Обновление pip..."
pip install --upgrade pip

echo "==> Установка Python-зависимостей..."
pip install -r requirements.txt

cat <<'EOF'
Готово.

Запустите приложение:
   source .venv/bin/activate
   python main.py

Подсказки:
- Можно указать REPO_URL, BRANCH или REPO_DIR перед запуском скрипта,
  чтобы задать свой форк/ветку или путь установки.
- Пример curl-запуска:
    curl -fsSL https://raw.githubusercontent.com/iligm/shellgramm2/main/termux_install.sh | bash
EOF

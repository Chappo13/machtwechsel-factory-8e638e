#!/usr/bin/env bash
# Разовая установка / обновление сборщика "Тайны Древних" на Mac (Apple Silicon).
# Безопасно запускать повторно — каждый запуск заново скачивает и
# переустанавливает проект рендера (идемпотентно: конечный результат одинаков
# независимо от того, запускали вы это один раз или десять).
#
# Использование:
#   ./setup.sh
# Переменные окружения (необязательно, иначе спросит один раз и запомнит):
#   TAINY_DASHBOARD_URL, TAINY_DASHBOARD_TOKEN
set -euo pipefail

TAINY_DIR="$HOME/Tainy"
RENDER_DIR="$TAINY_DIR/render"
CONF_FILE="$TAINY_DIR/dashboard.conf"
LOG_FILE="$TAINY_DIR/setup.log"

mkdir -p "$TAINY_DIR"
# Дублируем вывод в лог-файл, не теряя его в терминале/при двойном клике.
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') Установка/обновление «Тайны Древних» ==="

fail() {
  echo ""
  echo "ОШИБКА: $1"
  echo "Подробности — в файле $LOG_FILE"
  exit 1
}

# --- 1. Node.js -------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  cat <<'MSG'

Не найден Node.js — без него сборщик роликов работать не может.

Как установить (минут 5):
  1. Откройте в браузере https://nodejs.org
  2. Скачайте установщик "LTS" для macOS (.pkg) — подходит и для Apple Silicon (M1/M2/M3/M4)
  3. Запустите скачанный .pkg-файл и пройдите установку (спросит пароль от Mac)
  4. После установки запустите этот скрипт ещё раз — дважды кликните по нему в Finder

MSG
  fail "Node.js не установлен"
fi

NODE_MAJOR=$(node -e "console.log(process.versions.node.split('.')[0])")
if [ "$NODE_MAJOR" -lt 20 ]; then
  echo ""
  echo "Установлен Node.js $(node -v) — нужна версия 20 или новее."
  echo "Скачайте свежий установщик (.pkg) на https://nodejs.org и поставьте поверх текущей версии."
  fail "Node.js слишком старый"
fi
echo "Node.js $(node -v) — подходит."

# --- 2. Адрес пульта и токен -------------------------------------------------
if [ -f "$CONF_FILE" ] && [ -z "${TAINY_DASHBOARD_URL:-}" ]; then
  # shellcheck disable=SC1090
  source "$CONF_FILE"
fi
DASHBOARD_URL="${TAINY_DASHBOARD_URL:-}"
DASHBOARD_TOKEN="${TAINY_DASHBOARD_TOKEN:-}"
if [ -z "$DASHBOARD_URL" ] || [ -z "$DASHBOARD_TOKEN" ]; then
  echo ""
  echo "Нужен адрес пульта (дашборда) и токен доступа — их даёт Сергей."
  read -r -p "Адрес пульта (например https://pult.example.com): " DASHBOARD_URL
  read -r -p "Токен доступа: " DASHBOARD_TOKEN
fi
printf 'TAINY_DASHBOARD_URL=%q\nTAINY_DASHBOARD_TOKEN=%q\n' "$DASHBOARD_URL" "$DASHBOARD_TOKEN" > "$CONF_FILE"
chmod 600 "$CONF_FILE"

# --- 3. Скачиваем проект рендера --------------------------------------------
TMP_TAR="$TAINY_DIR/render.tar.gz.download"
rm -f "$TMP_TAR"
echo "Скачиваю проект рендера с пульта..."
DOWNLOAD_URL="${DASHBOARD_URL%/}/mac/render.tar.gz?token=${DASHBOARD_TOKEN}"
if ! curl -fsSL "$DOWNLOAD_URL" -o "$TMP_TAR"; then
  echo ""
  echo "Не удалось скачать проект рендера с $DASHBOARD_URL."
  echo "Проверьте:"
  echo "  - адрес и токен (файл $CONF_FILE — удалите его, чтобы ввести заново)"
  echo "  - что на пульте уже включена раздача mac/render.tar.gz"
  rm -f "$TMP_TAR"
  fail "скачивание проекта рендера не удалось"
fi
if [ ! -s "$TMP_TAR" ]; then
  rm -f "$TMP_TAR"
  fail "скачанный файл пустой — пульт вернул что-то не то"
fi

NEW_DIR="$TAINY_DIR/render.new"
rm -rf "$NEW_DIR"
mkdir -p "$NEW_DIR"
echo "Распаковываю..."
if ! tar -xzf "$TMP_TAR" -C "$NEW_DIR"; then
  rm -rf "$NEW_DIR" "$TMP_TAR"
  fail "архив повреждён или не распаковался"
fi
rm -f "$TMP_TAR"

# Архив может быть упакован как содержимое render/ прямо в корне, либо как
# один общий подкаталог (обычная структура tar/GitHub-архивов) — поддерживаем
# оба варианта, поднимая содержимое единственного подкаталога наверх.
if [ ! -f "$NEW_DIR/package.json" ]; then
  ENTRIES=$(find "$NEW_DIR" -mindepth 1 -maxdepth 1)
  ENTRY_COUNT=$(echo "$ENTRIES" | grep -c . || true)
  if [ "$ENTRY_COUNT" = "1" ] && [ -d "$ENTRIES" ] && [ -f "$ENTRIES/package.json" ]; then
    TMP_FLAT="$TAINY_DIR/render.flat"
    rm -rf "$TMP_FLAT"
    mv "$ENTRIES" "$TMP_FLAT"
    rm -rf "$NEW_DIR"
    mv "$TMP_FLAT" "$NEW_DIR"
  fi
fi

# Атомарная замена старой установки новой.
OLD_DIR="$TAINY_DIR/render.old"
rm -rf "$OLD_DIR"
if [ -d "$RENDER_DIR" ]; then mv "$RENDER_DIR" "$OLD_DIR"; fi
mv "$NEW_DIR" "$RENDER_DIR"
rm -rf "$OLD_DIR"

if [ ! -f "$RENDER_DIR/package.json" ]; then
  fail "в распакованном архиве нет render/package.json — структура архива не та, что ожидалась"
fi

# --- 4. npm ci ---------------------------------------------------------------
cd "$RENDER_DIR"
echo "Устанавливаю зависимости (npm ci) — может занять пару минут..."
if ! npm ci --no-audit --no-fund; then
  fail "npm ci не прошёл — подробности выше в логе"
fi

# --- 5. Браузер для рендера (без путей Playwright — Remotion качает свой) ---
echo "Готовлю браузер для рендера (Remotion Chrome Headless Shell для mac-arm64)..."
# В Remotion 4 браузер скачивается автоматически при первом рендере через
# ensureBrowser(); дёргаем это заранее, чтобы первый клик по "Собрать ролик"
# не ждал загрузки браузера молча.
node --input-type=module -e "
import('@remotion/renderer').then(({ ensureBrowser }) =>
  ensureBrowser ? ensureBrowser() : Promise.resolve()
).then(() => console.log('Браузер готов.'))
 .catch((e) => console.error('Не удалось подготовить браузер заранее (не страшно, попробуется при сборке):', e.message));
" || true

# --- 6. Ярлык на рабочем столе ------------------------------------------------
DESKTOP_CMD="$HOME/Desktop/Собрать ролик.command"
cat > "$DESKTOP_CMD" <<EOS
#!/usr/bin/env bash
exec node "$RENDER_DIR/mac/tainy-build.mjs" "\$@"
EOS
chmod +x "$DESKTOP_CMD"

echo ""
echo "Готово! На рабочем столе — ярлык «Собрать ролик.command»."
echo "Положите готовый архив tainy-*.zip в Загрузки и дважды кликните по ярлыку."

#!/usr/bin/env bash
# Бекап Health OS: локальний pg_dump ЗАВЖДИ + шифрований restic на зовнішній диск, КОЛИ підключено.
# Оригінали документів (health/documents) — єдині незамінні не-БД дані — теж у restic.
# Ключ (RESTIC_PASSWORD) — у .env (gitignored) + дубль у менеджері паролів (off-host).
#
# Розклад — через launchd (scripts/com.health-os.backup.plist). Ручний запуск: bash scripts/backup.sh
set -euo pipefail

# launchd має мінімальний PATH — додаємо restic/docker/homebrew
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# .env містить усе: POSTGRES_* + RESTIC_*/DOCS_DIR (один файл, поза git)
# macOS: launchd jobs can't read ~/Desktop or ~/Documents (TCC). Install a copy of this script
# elsewhere and point it at the env file / state dir: scripts/install_launchd.sh does that.
ENV_FILE="${HEALTH_OS_ENV_FILE:-.env}"
STATE="${HEALTH_OS_STATE_DIR:-data}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

CONTAINER="${POSTGRES_CONTAINER:-health_os_db}"
DOCS_DIR="${DOCS_DIR:-../health/documents}"
TS="$(date +%Y%m%d_%H%M%S)"
DUMP="$STATE/backups/pg_${TS}.dump"
mkdir -p "$STATE/backups"

# a failed backup is logged and shown, never silent
. "$(dirname "${BASH_SOURCE[0]}")/_ensure_docker.sh"
on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') backup FAILED (exit $rc)" >> "$STATE/backup.log"
    notify "Health OS — backup failed" "No backup was made (exit $rc). Details: $STATE/backup.log"
  fi
}
trap on_exit EXIT
ensure_docker "$CONTAINER"

echo "[1/3] pg_dump (локальний, завжди)…"
docker exec "$CONTAINER" pg_dump -U "${POSTGRES_USER:-health}" -Fc "${POSTGRES_DB:-health_os}" > "$DUMP"
echo "  → $DUMP ($(du -h "$DUMP" | cut -f1))"

# restic — якщо репозиторій доступний (шифрує сам бекап паролем, AES-256)
if [ -n "${RESTIC_REPOSITORY:-}" ] && [ -n "${RESTIC_PASSWORD:-}" ] && [ -d "${RESTIC_REPOSITORY}" ]; then
  echo "[2/2] restic backup (зашифровано) → ${RESTIC_REPOSITORY} …"
  BACKUP_PATHS=("$DUMP")
  [ -d "$DOCS_DIR" ] && BACKUP_PATHS+=("$DOCS_DIR")
  restic backup "${BACKUP_PATHS[@]}" --tag health-os --host health-os
  restic forget --keep-daily 7 --keep-weekly 8 --keep-monthly 12 --prune || true
  rm -f "$DUMP"   # плейнтекст-дамп більше не потрібен — усе в зашифрованому репо
  echo "$(date '+%Y-%m-%d %H:%M:%S') backup OK (restic, encrypted)" >> "$STATE/backup.log"
else
  echo "[2/2] restic недоступний (${RESTIC_REPOSITORY:-не задано}) → лишаю локальний дамп (fallback), тримаю 3 останні."
  ls -1t "$STATE"/backups/pg_*.dump 2>/dev/null | tail -n +4 | xargs -r rm -f
  echo "$(date '+%Y-%m-%d %H:%M:%S') backup LOCAL-ONLY (plaintext fallback) dump=${DUMP##*/}" >> "$STATE/backup.log"
fi
echo "OK: бекап $TS завершено."

#!/usr/bin/env bash
# Тест відновлення — відновлює останній pg-дамп у тимчасову базу й перевіряє цілісність.
# Нічого не чіпає в робочій базі. Потребує docker cp (pg_restore має бути Postgres 16).
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${HEALTH_OS_ENV_FILE:-.env}"
STATE="${HEALTH_OS_STATE_DIR:-data}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

CONTAINER="${POSTGRES_CONTAINER:-health_os_db}"
PG_USER="${POSTGRES_USER:-health}"
PG_DB="${POSTGRES_DB:-health_os}"

TMPDIR="$(mktemp -d)"
. "$(dirname "${BASH_SOURCE[0]}")/_ensure_docker.sh"
on_exit() {
  local rc=$?
  rm -rf "$TMPDIR"
  if [ "$rc" -ne 0 ]; then
    echo "$(date +%Y-%m-%d_%H:%M:%S) FAILED (exit $rc)" >> "$STATE/restore_test.log"
    notify "Health OS — restore test failed" "The weekly restore test failed (exit $rc)."
  fi
}
trap on_exit EXIT
ensure_docker "$CONTAINER"

# Джерело дампа: restic (зовнішній диск) якщо доступний, інакше — останній локальний дамп.
if [ -n "${RESTIC_REPOSITORY:-}" ] && [ -n "${RESTIC_PASSWORD:-}" ] && [ -d "${RESTIC_REPOSITORY}" ]; then
  echo "[1/5] restic restore останнього снапшоту (зовнішній диск)…"
  restic restore latest --target "$TMPDIR"
  DUMP="$(find "$TMPDIR" -name 'pg_*.dump' | sort | tail -1)"
else
  echo "[1/5] зовнішній диск недоступний — беру останній ЛОКАЛЬНИЙ дамп…"
  DUMP="$(ls -1t "$STATE"/backups/pg_*.dump 2>/dev/null | head -1)"
fi
[ -n "${DUMP:-}" ] && [ -f "$DUMP" ] || { echo "ПОМИЛКА: дамп не знайдено"; exit 1; }
echo "  Дамп: $DUMP ($(du -h "$DUMP" | cut -f1))"

echo "[2/5] docker cp дампа в контейнер…"
docker cp "$DUMP" "${CONTAINER}:/tmp/restore_test.dump"

echo "[3/5] створення тимчасової БД…"
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$PG_DB" \
  -c "DROP DATABASE IF EXISTS health_os_restore_test;" \
  -c "CREATE DATABASE health_os_restore_test;"

echo "[4/5] pg_restore (Postgres 16 → Postgres 16)…"
docker exec "$CONTAINER" pg_restore -U "$PG_USER" -d health_os_restore_test \
  --no-privileges --no-owner /tmp/restore_test.dump 2>&1 | head -20 || true

echo "[5/5] перевірка цілісності…"
CNT=$(docker exec "$CONTAINER" psql -U "$PG_USER" -d health_os_restore_test -tAc \
  "SELECT count(*) FROM observation_types;")
OBS=$(docker exec "$CONTAINER" psql -U "$PG_USER" -d health_os_restore_test -tAc \
  "SELECT count(*) FROM observations;")
ACT=$(docker exec "$CONTAINER" psql -U "$PG_USER" -d health_os_restore_test -tAc \
  "SELECT count(*) FROM physical_activities;")
DX=$(docker exec "$CONTAINER" psql -U "$PG_USER" -d health_os_restore_test -tAc \
  "SELECT count(*) FROM diagnoses;")

# Cleanup
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$PG_DB" \
  -c "DROP DATABASE IF EXISTS health_os_restore_test;" >/dev/null
docker exec "$CONTAINER" rm -f /tmp/restore_test.dump

TS="$(date +%Y-%m-%d_%H:%M:%S)"
if [ "${CNT:-0}" -gt 0 ]; then
  echo ""
  echo "✅ RESTORE TEST PASSED [$TS]"
  echo "   observation_types  : $CNT"
  echo "   observations       : $OBS"
  echo "   physical_activities: $ACT"
  echo "   diagnoses          : $DX"
  echo "$TS OK obs=$OBS act=$ACT dx=$DX" >> "$STATE/restore_test.log"
else
  echo "❌ RESTORE FAILED [$TS] — порожня база"; exit 1
fi

# Sourced by backup.sh and restore_test.sh (not run directly).
#
# On macOS Docker Desktop is often not running (after a reboot or once it's quit). pg_dump then
# failed with "Cannot connect to the Docker daemon" and the day's backup was skipped without
# anyone noticing. ensure_docker starts Docker Desktop and waits for the database; notify makes
# a failure visible.

notify() {  # title message — macOS notification (stays on this machine) + stderr; never fails
  echo "[health-os] $1: $2" >&2
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${2//\"/\'}\" with title \"${1//\"/\'}\"" \
      >/dev/null 2>&1 || true
  fi
}

ensure_docker() {  # container — 0 once the Docker daemon is up and the container is healthy
  local container="$1" i
  if ! docker info >/dev/null 2>&1; then
    if [ "$(uname)" = "Darwin" ] && [ -d /Applications/Docker.app ]; then
      echo "Docker is not running — starting Docker Desktop…"
      open -ga Docker || true
    fi
    for i in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
    docker info >/dev/null 2>&1 || { echo "Docker daemon did not come up"; return 1; }
  fi
  for i in $(seq 1 60); do
    case "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null)" in
      healthy|running) return 0 ;;
      exited|created) docker start "$container" >/dev/null 2>&1 || true ;;
    esac
    sleep 2
  done
  echo "container $container is not healthy"
  return 1
}

#!/usr/bin/env bash
# Install the daily backup + weekly restore test as launchd jobs (macOS).
#
# launchd jobs can't read ~/Desktop, ~/Documents or ~/Downloads (TCC: "Operation not permitted"),
# so the jobs must not run scripts from a checkout there. This copies the two scripts and the
# few settings they need to an install dir outside those folders and points launchd at it.
#
#   bash scripts/install_launchd.sh            # install / update
#   HEALTH_OS_INSTALL_DIR=~/somewhere bash scripts/install_launchd.sh
#
# Re-run after changing backup.sh / restore_test.sh or the restic settings in .env.
# Not copied: DOCS_DIR — originals on Desktop/Documents are unreadable for launchd, so back them
# up by running scripts/backup.sh manually (or grant Full Disk Access if you want it automatic).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${HEALTH_OS_INSTALL_DIR:-$HOME/Library/health-os-runner}"
STATE="$DEST/state"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$DEST" "$STATE" "$AGENTS"
chmod 700 "$DEST"

cp "$ROOT/scripts/backup.sh" "$ROOT/scripts/restore_test.sh" "$ROOT/scripts/_ensure_docker.sh" \
  "$DEST/"

# only what the jobs need (no API keys, no DB URLs, no DOCS_DIR)
ENV_OUT="$DEST/backup.env"
umask 077
grep -E '^(POSTGRES_USER|POSTGRES_DB|POSTGRES_CONTAINER|RESTIC_REPOSITORY|RESTIC_PASSWORD)=' \
  "$ROOT/.env" > "$ENV_OUT" || true
chmod 600 "$ENV_OUT"

write_plist() {  # label script hour minute [weekday]
  local label="$1" script="$2" hour="$3" minute="$4" weekday="${5:-}"
  local wd=""
  [ -n "$weekday" ] && wd="<key>Weekday</key><integer>$weekday</integer>"
  cat > "$AGENTS/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$label</string>
    <key>ProgramArguments</key>
    <array><string>/bin/bash</string><string>$DEST/$script</string></array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HEALTH_OS_ENV_FILE</key><string>$ENV_OUT</string>
        <key>HEALTH_OS_STATE_DIR</key><string>$STATE</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>$wd<key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$minute</integer></dict>
    <key>StandardOutPath</key><string>$STATE/$label.log</string>
    <key>StandardErrorPath</key><string>$STATE/$label.log</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist"
  echo "installed $label → $DEST/$script"
}

write_plist com.health-os.backup backup.sh 13 0
write_plist com.health-os.restore-test restore_test.sh 13 30 0

echo "Logs: $STATE/   Test now: launchctl kickstart -k gui/$(id -u)/com.health-os.backup"

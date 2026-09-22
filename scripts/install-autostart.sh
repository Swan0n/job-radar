#!/bin/bash
# Ставит фоновый агент macOS: сервис поднимается при входе в систему
# и переживает перезагрузку. Прогоны при этом не запускаются сами — только
# по кнопке, если в настройках не включено ежедневное обновление.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.jobradar.app.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT/data/logs"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jobradar.app</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PROJECT/scripts/run.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PROJECT/data/logs/stdout.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/data/logs/stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Автозапуск включён. Сервис слушает http://127.0.0.1:8777"
echo "Выключить: launchctl unload $PLIST && rm $PLIST"

#!/bin/bash
# Starts the whole Invoice Agent ON THE JETSON: camera (localhost only), local AI (localhost only),
# and the web app (network, PIN-protected). Safe to run again: restarts the app, keeps what is running.
#   bash ~/alphahack/jetson/start_all.sh
APP="$HOME/alphahack"
LOG="$APP/data"
mkdir -p "$LOG"
export PATH="$HOME/.local/bin:$PATH"

# 1. camera on 127.0.0.1:8090
if ! pgrep -f "[c]amera_server.py" >/dev/null; then
  HOST=127.0.0.1 setsid nohup python3 "$APP/jetson/camera_server.py" > "$LOG/camera.log" 2>&1 < /dev/null &
fi

# 2. local AI (Ollama) on 127.0.0.1:11434, model kept loaded
bash "$APP/jetson/setup_local_ai.sh" start

# 3. web app on 0.0.0.0:8400 (restart to load the latest code). Make sure NO old copy survives:
#    a stuck old copy kept serving old code next to the new one once.
pkill -f "python3 $APP/server[.]py" 2>/dev/null
for i in $(seq 1 10); do pgrep -f "python3 $APP/server[.]py" >/dev/null || break; sleep 0.5; done
pkill -9 -f "python3 $APP/server[.]py" 2>/dev/null; sleep 0.5
for i in $(seq 1 20); do ss -ltn 2>/dev/null | grep -q ":8400 " || break; sleep 0.5; done   # wait for the port
cd "$APP" && setsid nohup python3 "$APP/server.py" > "$LOG/server.log" 2>&1 < /dev/null &

for i in $(seq 1 30); do
  if curl -s -m 2 localhost:8400/api/session >/dev/null; then break; fi; sleep 1
done
curl -s -m 3 localhost:8090/health >/dev/null && echo "camera  OK" || echo "camera  NOT RUNNING (see $LOG/camera.log)"
curl -s -m 3 localhost:11434/api/tags >/dev/null && echo "AI      OK" || echo "AI      NOT RUNNING (see ~/ollama.log)"
curl -s -m 3 localhost:8400/api/session >/dev/null && echo "web app OK" || echo "web app NOT RUNNING (see $LOG/server.log)"
echo "Open from the laptop:  http://192.168.55.1:8400  (USB cable)"
for ip in $(hostname -I); do case $ip in 192.168.55.*|172.*) ;; *) echo "                   or  http://$ip:8400" ;; esac; done

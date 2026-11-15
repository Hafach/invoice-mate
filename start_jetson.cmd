@echo off
REM Starts the camera server and the local AI on the Jetson. Run after the Jetson boots.
REM Tries home Wi-Fi, USB cable, mDNS name, then Tailscale.
for %%H in (192.168.10.175 192.168.55.1 elevai.local 100.80.250.116) do (
  ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new elevai@%%H "pgrep -f '[c]amera_server.py' >/dev/null && echo camera already running || (setsid nohup python3 /home/elevai/camera_server.py > /home/elevai/camera_server.log 2>&1 < /dev/null & sleep 6; tail -2 /home/elevai/camera_server.log); if [ -x /home/elevai/ollama/bin/ollama ]; then bash /home/elevai/setup_local_ai.sh start; else echo 'local AI not installed yet: run setup_local_ai.sh on a fast connection'; fi" && goto :done
)
echo Could not reach the Jetson.
:done

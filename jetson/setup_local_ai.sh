#!/bin/bash
# One-time setup of the local AI on the Jetson (no sudo). Safe to re-run: downloads RESUME.
#   bash setup_local_ai.sh            # install Ollama + pull the model, then start it
#   bash setup_local_ai.sh start      # only (re)start the AI server
set -e
MODEL="${OLLAMA_MODEL:-qwen2.5vl:3b}"
DIR="$HOME/ollama"
DL="$HOME/ollama_dl"
export PATH="$DIR/bin:$PATH"
export LD_LIBRARY_PATH="$DIR/lib/ollama:$LD_LIBRARY_PATH"

start() {
  if pgrep -x ollama >/dev/null; then echo "ollama already running"; return; fi
  # 127.0.0.1: only the app running on the Jetson may use the model (not the network)
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=60m setsid nohup "$DIR/bin/ollama" serve > "$HOME/ollama.log" 2>&1 < /dev/null &
  for i in $(seq 1 30); do curl -s localhost:11434/api/tags >/dev/null && { echo "ollama running on :11434"; return; }; sleep 1; done
  echo "ollama did not start, see ~/ollama.log"; exit 1
}

if [ "$1" = "start" ]; then start; exit 0; fi

mkdir -p "$DIR" "$DL"
for f in ollama-linux-arm64.tar.zst ollama-linux-arm64-jetpack6.tar.zst; do
  if [ -f "$DL/$f.done" ]; then echo "already have $f"; continue; fi
  echo "downloading $f (resumes if interrupted)"
  curl -fL --retry 10 --retry-delay 5 -C - -o "$DL/$f" "https://ollama.com/download/$f"
  tar --zstd -xf "$DL/$f" -C "$DIR" && touch "$DL/$f.done" && rm -f "$DL/$f"
done
"$DIR/bin/ollama" --version || true
start
echo "pulling model $MODEL (resumes if interrupted)"
"$DIR/bin/ollama" pull "$MODEL"
echo "LOCAL AI READY: $MODEL"

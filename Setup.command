#!/bin/bash
# One-time setup for the Twitch TTS Bot on macOS.
# First time: right-click -> Open (to get past the Gatekeeper warning).
cd "$(dirname "$0")"
echo "================================================"
echo "   Twitch TTS Bot - setup (macOS)"
echo "================================================"

# Prefer Python 3.12, then 3.11 (PyTorch has no 3.14 build yet).
PY=""
for c in python3.12 python3.11; do
  command -v "$c" >/dev/null 2>&1 && PY="$c" && break
done
if [ -z "$PY" ]; then
  echo "Python 3.12 or 3.11 not found."
  echo "Install with Homebrew:  brew install python@3.12"
  echo "or from https://www.python.org/downloads/"
  read -n 1 -s -r -p "Press any key to close."; exit 1
fi
echo "Using $PY ($($PY --version))"

[ -d "$HOME/tts-bot" ] || "$PY" -m venv "$HOME/tts-bot"
source "$HOME/tts-bot/bin/activate"
echo "Installing packages (PyTorch is large; this may take a few minutes) ..."
pip install --upgrade pip
pip install pocket-tts numpy sounddevice websockets aiohttp certifi pystray pillow

if command -v brew >/dev/null 2>&1; then
  brew list blackhole-2ch >/dev/null 2>&1 || brew install blackhole-2ch \
    || echo "Install BlackHole manually: https://existential.audio/blackhole/"
else
  echo "Homebrew not found -> install BlackHole manually: https://existential.audio/blackhole/"
fi

echo "Pre-downloading model + default voice ..."
python -c "from pocket_tts import TTSModel; m=TTSModel.load_model(language='english'); m.get_state_for_audio_prompt('alba'); print('Model ready.')" \
  || echo "(model will download on first start)"

echo ""
echo "Setup complete."
echo "1) Set output_device in config.json to \"BlackHole 2ch\" (+ set channel/voice)."
echo "2) Double-click 'Start TTS Bot.command'."
read -n 1 -s -r -p "Press any key to close."

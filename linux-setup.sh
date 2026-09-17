#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "============================================"
echo "   Twitch TTS Bot - setup (Linux)"
echo "============================================"

# Prefer Python 3.12, then 3.11 (PyTorch has no 3.14 build yet).
PY=""
for c in python3.12 python3.11; do
  command -v "$c" >/dev/null 2>&1 && PY="$c" && break
done
if [ -z "$PY" ]; then
  echo "Python 3.12 or 3.11 not found. Install it via your package manager:"
  echo "  Fedora/Nobara : sudo dnf install python3.12"
  echo "  Debian/Ubuntu : sudo apt install python3.12 python3.12-venv"
  exit 1
fi
echo "Using $PY ($($PY --version))"

# PortAudio is needed by sounddevice
if ! ldconfig -p 2>/dev/null | grep -qi libportaudio; then
  echo "Note: PortAudio may be required for audio output:"
  echo "  Fedora/Nobara : sudo dnf install portaudio"
  echo "  Debian/Ubuntu : sudo apt install libportaudio2"
fi

[ -d "$HOME/tts-bot" ] || "$PY" -m venv "$HOME/tts-bot"
source "$HOME/tts-bot/bin/activate"
pip install --upgrade pip
pip install pocket-tts numpy sounddevice websockets aiohttp certifi pystray pillow

echo "Pre-downloading model + default voice ..."
python -c "from pocket_tts import TTSModel; m=TTSModel.load_model(language='english'); m.get_state_for_audio_prompt('alba'); print('Model ready.')" \
  || echo "(model will download on first start)"

echo ""
echo "Setup complete."
echo "Audio for OBS, two options:"
echo "  A) Simplest: leave output_device = null, capture the bot in OBS via"
echo "     'Application Audio Capture' (PipeWire) or Desktop Audio."
echo "  B) Dedicated sink:"
echo "       pactl load-module module-null-sink sink_name=TTS sink_properties=device.description=TTS"
echo "     then set output_device to \"TTS\" and capture 'Monitor of TTS' in OBS."
echo "Then edit config.json (channel, voice) and run ./linux-start.sh"

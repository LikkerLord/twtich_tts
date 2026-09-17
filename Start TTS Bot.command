#!/bin/bash
# Double-click launcher for the TTS Bot GUI on macOS.
# Put this file next to tts_gui.py. On first use you may need to make it
# executable once:  chmod +x "Start TTS Bot.command"
# macOS opens .command files in Terminal on double-click.

cd "$(dirname "$0")"

# Activate the virtual environment if it exists (adjust the path if needed).
if [ -f "$HOME/tts-bot/bin/activate" ]; then
    source "$HOME/tts-bot/bin/activate"
fi

python3 tts_bot.py

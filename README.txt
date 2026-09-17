Twitch TTS Bot — quick start (macOS / Windows / Linux)
======================================================

Reads your Twitch chat aloud with a local text-to-speech voice. After a
one-time model download it runs fully offline.

What's in this folder
---------------------
  tts_bot.py             The bot (same on every OS).
  config.json            ALL settings — edit this file.
  test.html              Open in a browser to test /tts /skip /clear.
  abbreviations.json     Optional: chat shorthand -> spoken words.
  emotes.json            Optional: third-party emotes to skip.

  macOS   : Setup.command        + Start TTS Bot.command
  Windows : windows-setup.bat    + windows-start.bat
  Linux   : linux-setup.sh       + linux-start.sh

Requirements
------------
Python 3.12 or 3.11 (NOT 3.13/3.14 — PyTorch has no build for those yet).
The setup script looks for a suitable Python and tells you if none is found.

First time
----------
macOS   : double-click "Setup.command". If macOS blocks it (downloaded file):
          right-click -> Open -> Open.
Windows : double-click "windows-setup.bat". If SmartScreen warns:
          "More info" -> "Run anyway".
Linux   : run "./linux-setup.sh" in a terminal (or mark executable and use
          "Run in Terminal"). You may need PortAudio (the script tells you).

The setup installs everything and pre-downloads the voice (a few minutes).

Audio into OBS (per OS)
-----------------------
The bot plays to the device named in config.json ("output_device").
  macOS   : install BlackHole (https://existential.audio/blackhole/),
            set output_device to "BlackHole 2ch",
            add OBS "Audio Input Capture" on BlackHole 2ch.
  Windows : install VB-CABLE (https://vb-audio.com/Cable/),
            set output_device to "CABLE Input (VB-Audio Virtual Cable)",
            add OBS "Audio Input Capture" on "CABLE Output".
  Linux   : easiest — leave output_device = null and add OBS
            "Application Audio Capture" (PipeWire) on the python process;
            or create a null sink (see linux-setup.sh output) and target it.
Simplest everywhere: leave output_device = null (plays to your normal output)
and let OBS capture Desktop Audio — the downside is you hear the TTS too.

Every time
----------
macOS   : "Start TTS Bot.command"
Windows : "windows-start.bat"
Linux   : "./linux-start.sh"
Then write a message in your chat to test. Close the window / Ctrl+C to stop.

Settings
--------
Edit config.json (annotated; // lines are comments), save, restart the bot.
  mode            "twitch" (read chat) or "http" (Firebot sends text)
  voice           built-in voice (alba, anna, michael, vera, jane, ...)
  output_device   see "Audio into OBS" above
  filters         optional anti-abuse filters (repeats, spam, copypasta)
  firebot_actions optional: run a Firebot preset when a filter fires
  show_tray_icon  true (default): also show a system-tray icon with
                  Open config folder / Skip / Clear / Quit

Control (works in both modes)
-----------------------------
A small local server always runs. Trigger from a browser, Stream Deck, or
Firebot HTTP Request effect:
  http://127.0.0.1:5050/skip     stop the current message, play the next
  http://127.0.0.1:5050/clear    drop the whole queue and stop the current

Notes
-----
- Everything runs locally/offline after the first model download.
- If audio endings sound clipped, raise tail_padding_seconds in config.json.

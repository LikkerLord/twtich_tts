@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Twitch TTS Bot - setup (Windows)
echo ============================================
echo.

REM Prefer Python 3.12, then 3.11 (PyTorch has no 3.14 build yet).
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD (
  py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
)
if not defined PYCMD (
  echo Python 3.12 or 3.11 was not found.
  echo Install it from https://www.python.org/downloads/
  echo During install, tick "Add Python to PATH".
  pause
  exit /b 1
)
echo Using %PYCMD%

if not exist "%USERPROFILE%\tts-bot\Scripts\activate.bat" (
  echo Creating virtual environment ...
  %PYCMD% -m venv "%USERPROFILE%\tts-bot"
)
call "%USERPROFILE%\tts-bot\Scripts\activate.bat"

echo Installing packages (PyTorch is large; this may take a while) ...
python -m pip install --upgrade pip
pip install pocket-tts numpy sounddevice websockets aiohttp certifi pystray pillow

echo.
echo Pre-downloading model + default voice ...
python -c "from pocket_tts import TTSModel; m=TTSModel.load_model(language='english'); m.get_state_for_audio_prompt('alba'); print('Model ready.')"

echo.
echo ============================================
echo  Setup complete.
echo  1) Install VB-CABLE: https://vb-audio.com/Cable/
echo  2) Edit config.json: set channel, voice, and
echo     output_device to "CABLE Input (VB-Audio Virtual Cable)"
echo  3) Double-click windows-start.bat
echo ============================================
pause

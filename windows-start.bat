@echo off
cd /d "%~dp0"
call "%USERPROFILE%\tts-bot\Scripts\activate.bat"
python tts_bot.py
pause

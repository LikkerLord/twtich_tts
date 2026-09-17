# PyInstaller spec for the Twitch TTS Bot.
# Run from the repo root:  pyinstaller packaging/tts_bot.spec --noconfirm
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
# Pull in everything these packages need (torch is the big one).
for pkg in ("torch", "pocket_tts", "sentencepiece", "sounddevice", "aiohttp", "certifi",
            "pystray", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# Editable defaults shipped inside the app (seeded to a user folder on first run).
datas += [
    ("config.json", "."),
    ("abbreviations.json", "."),
    ("emotes.json", "."),
    ("test.html", "."),
    ("README.txt", "."),
]

a = Analysis(
    ["tts_bot.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="tts-bot",
    console=False,              # tray app: no console window, tray icon instead
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="tts-bot")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Twitch TTS Bot.app",
        bundle_identifier="com.example.twitchttsbot",
        info_plist={"CFBundleName": "Twitch TTS Bot"},
    )

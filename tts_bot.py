#!/usr/bin/env python3
"""
================================================================================
 Twitch TTS Bot  --  config-driven, runs as a system-tray app
================================================================================
 All settings live in config.json (next to this file). Edit that, then restart.
 Synthesis: Kyutai Pocket TTS (built-in voice, fully local after first download).
 Output:    via 'sounddevice' to a named device (Mac: BlackHole, OBS captures it).

 config.json keys:
   mode                "twitch" (read chat directly) or "http" (Firebot calls us)
   channel             your Twitch channel, lowercase, no '#' (twitch mode)
   voice               built-in voice name, e.g. alba, anna, michael, vera, jane
   language            "english"
   output_device       device name substring, or null for the system default
   read_username       true/false - speak the sender's name (twitch mode only)
   username_format     template, e.g. "{user} says: {text}" (twitch mode only)
   min_chars/max_chars length limits
   cooldown_seconds    minimum seconds between messages per user (0 = off)
   tail_padding_seconds trailing silence so endings aren't clipped
   ignored_users       bot accounts to skip
   ignore_prefixes     message prefixes treated as commands and skipped
   filters             optional anti-abuse filters (repeated words/chars, word
                       spam, over-long words, copypasta) - each switchable
   firebot_actions     optional: run a Firebot preset effect list when a filter
                       fires (maps each filter to a preset list ID)
   http_host/http_port local HTTP server address (http mode)
   show_tray_icon      true/false - run as a system-tray app (default true);
                       falls back to a plain console loop if the tray backend
                       isn't available (e.g. headless Linux)

 Run:
   python3 tts_bot.py

 Tray menu (when show_tray_icon is on): open the config folder, open the log
 file (frozen builds only), skip the current message, clear the queue, quit.

 Control endpoints (a small local server runs in BOTH modes):
   http://127.0.0.1:5050/skip    abort the current message, play the next
   http://127.0.0.1:5050/clear   drop the whole queue and abort the current
   http://127.0.0.1:5050/tts     speak text (used by Firebot in "http" mode)
================================================================================
"""

import asyncio
import json
import os
import random
import re
import shutil
import ssl
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import sounddevice as sd
from pocket_tts import TTSModel


def _user_config_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "twitch-tts-bot"


class _Tee:
    """Writes to every given stream, skipping any that are None (e.g. a
    windowed Windows build has no real sys.stdout) or that error out."""

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


LOG_FILE = None
if getattr(sys, "frozen", False):
    # Installed/frozen app: keep editable config + JSON in a per-user folder,
    # seeded once from the files bundled inside the app.
    _RES_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = _user_config_dir()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # Always keep a log file, on every OS - not just when sys.stdout is None
    # (that only happens on windowed Windows builds; on Linux/macOS a
    # console=False build can still have a real, just-not-visible stdout, so
    # a crash there would otherwise vanish with nothing to inspect). Tee so a
    # terminal launch still shows live output too.
    LOG_FILE = APP_DIR / "tts_bot.log"
    _log_fh = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, _log_fh)
    sys.stderr = _Tee(sys.stderr, _log_fh)
    for _fn in ("config.json", "abbreviations.json", "emotes.json"):
        _dst = APP_DIR / _fn
        if not _dst.exists() and (_RES_DIR / _fn).exists():
            shutil.copy(_RES_DIR / _fn, _dst)
    print(f"Config folder: {APP_DIR}")
    TEST_HTML_PATH = _RES_DIR / "test.html"
else:
    APP_DIR = Path(__file__).parent
    TEST_HTML_PATH = APP_DIR / "test.html"

CONFIG_FILE = APP_DIR / "config.json"
ABBR_FILE = APP_DIR / "abbreviations.json"
EMOTE_FILE = APP_DIR / "emotes.json"

DEFAULTS = {
    "mode": "twitch",
    "channel": "yourchannelname",
    "voice": "alba",
    "language": "english",
    "output_device": None,
    "read_username": True,
    "username_format": "{user} says: {text}",
    "min_chars": 1,
    "max_chars": 300,
    "cooldown_seconds": 0,
    "tail_padding_seconds": 0.4,
    "ignored_users": ["nightbot", "streamelements", "streamlabs", "moobot"],
    "ignore_prefixes": ["!", "/"],
    "filters": {},
    "firebot_actions": {},
    "http_host": "127.0.0.1",
    "http_port": 5050,
    "show_tray_icon": True,
}


def _load_json(path, default, allow_comments=False):
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return default
    if allow_comments:
        # Drop whole-line // comments so config.json can be annotated.
        raw = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("//"))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path.name} is not valid JSON: {e}")


# --------------------------- Load configuration ------------------------------
_cfg = {**DEFAULTS, **_load_json(CONFIG_FILE, {}, allow_comments=True)}

MODE = _cfg["mode"]
CHANNEL = str(_cfg["channel"]).lower().lstrip("#")
VOICE = _cfg["voice"]
LANGUAGE = _cfg["language"]
OUTPUT_DEVICE = _cfg["output_device"] or None
READ_USERNAME = bool(_cfg["read_username"])
USERNAME_FORMAT = _cfg["username_format"]
MIN_CHARS = int(_cfg["min_chars"])
MAX_CHARS = int(_cfg["max_chars"])
COOLDOWN_SECONDS = float(_cfg["cooldown_seconds"])
TAIL_PADDING_SECONDS = float(_cfg["tail_padding_seconds"])
IGNORED_USERS = {str(u).lower() for u in _cfg["ignored_users"]}
IGNORE_PREFIXES = tuple(_cfg["ignore_prefixes"])
HTTP_HOST = _cfg["http_host"]
HTTP_PORT = int(_cfg["http_port"])
SHOW_TRAY_ICON = bool(_cfg["show_tray_icon"])
# -----------------------------------------------------------------------------

TWITCH_WS = "wss://irc-ws.chat.twitch.tv:443"

# Build an SSL context from certifi so wss:// works even when macOS Python has
# no local CA certificates (the common "CERTIFICATE_VERIFY_FAILED" on Mac).
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PRIVMSG_RE = re.compile(r":(\w+)!\w+@[\w.]+ PRIVMSG #\w+ :(.*)")
_last_spoken: dict[str, float] = {}


# --------------------------- Abbreviations / emotes --------------------------
_abbr_raw = _load_json(ABBR_FILE, {})
ABBREVIATIONS = {str(k).lower(): str(v) for k, v in _abbr_raw.items()} if _abbr_raw else {}
_ABBR_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(ABBREVIATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
) if ABBREVIATIONS else None

_emote_list = _load_json(EMOTE_FILE, [])
_EMOTE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(e) for e in sorted(_emote_list, key=len, reverse=True)) + r")\b"
) if _emote_list else None


def expand_abbreviations(text):
    text = re.sub(r"\blo+l\b", "lol", text, flags=re.IGNORECASE)
    text = re.sub(r"\blma+o+\b", "lmao", text, flags=re.IGNORECASE)
    if _ABBR_PATTERN:
        text = _ABBR_PATTERN.sub(lambda m: ABBREVIATIONS[m.group(0).lower()], text)
    return text


def strip_custom_emotes(text):
    if _EMOTE_PATTERN:
        text = _EMOTE_PATTERN.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def strip_native_emotes(message, emotes_tag):
    if not emotes_tag:
        return message
    ranges = []
    for chunk in emotes_tag.split("/"):
        _id, _, positions = chunk.partition(":")
        for pos in positions.split(","):
            a, _, b = pos.partition("-")
            try:
                ranges.append((int(a), int(b)))
            except ValueError:
                pass
    if not ranges:
        return message
    chars = list(message)
    for a, b in ranges:
        for i in range(a, min(b, len(chars) - 1) + 1):
            chars[i] = None
    result = "".join(c for c in chars if c is not None)
    return re.sub(r"\s{2,}", " ", result).strip()
# -----------------------------------------------------------------------------


# ------------------------------ Abuse filters --------------------------------
# All optional, each switchable via the "filters" block in config.json.
_F = _cfg.get("filters", {}) or {}
F_COLLAPSE_CHARS = bool(_F.get("collapse_char_runs", True))
F_MAX_CHAR_RUN = max(1, int(_F.get("max_char_run", 3)))
F_COLLAPSE_WORDS = bool(_F.get("collapse_word_repeats", True))
F_MAX_WORD_REPEATS = max(1, int(_F.get("max_word_repeats", 3)))
F_SKIP_SPAM = bool(_F.get("skip_word_spam", False))
F_SPAM_MIN_WORDS = int(_F.get("spam_min_words", 6))
F_SPAM_RATIO = float(_F.get("spam_ratio", 0.6))
F_MAX_WORD_LENGTH = int(_F.get("max_word_length", 0))            # 0 = off
F_BLOCK_REPEATS = bool(_F.get("block_repeated_messages", False))

_last_message: dict[str, str] = {}


def _collapse_char_runs(text):
    # "aaaaaa" -> F_MAX_CHAR_RUN a's, "!!!!!" -> capped too
    return re.sub(r"(.)\1{%d,}" % F_MAX_CHAR_RUN,
                  lambda m: m.group(1) * F_MAX_CHAR_RUN, text)


def _collapse_word_repeats(text):
    # "lol lol lol lol" -> keep at most F_MAX_WORD_REPEATS in a row
    out, prev, run = [], None, 0
    for w in text.split():
        key = w.lower()
        run = run + 1 if key == prev else 1
        prev = key
        if run <= F_MAX_WORD_REPEATS:
            out.append(w)
    return " ".join(out)


def _is_word_spam(text):
    # True if one word makes up >= spam_ratio of a long-enough message
    words = [w.lower() for w in text.split()]
    if len(words) < F_SPAM_MIN_WORDS:
        return False
    return max(Counter(words).values()) / len(words) >= F_SPAM_RATIO


# --------------------------- Firebot actions ---------------------------------
# When a filter fires, optionally trigger a Firebot preset effect list so you
# can react (timeout, warn in chat, log, ...). Configured in config.json under
# "firebot_actions"; each filter maps to a preset list ID (empty = no action).
_FB = _cfg.get("firebot_actions", {}) or {}
FB_ENABLED = bool(_FB.get("enabled", False))
FB_API_BASE = str(_FB.get("api_base", "http://localhost:7472")).rstrip("/")
FB_ASYNC = bool(_FB.get("async", True))
FB_PRESETS = {k: str(v) for k, v in (_FB.get("presets", {}) or {}).items() if v}


async def _post_firebot(preset_id, user, message, filter_name):
    from aiohttp import ClientSession, ClientTimeout
    url = f"{FB_API_BASE}/api/v1/effects/preset/{preset_id}"
    if FB_ASYNC:
        url += "/run"          # async: Firebot doesn't wait for effects to finish
    payload = {"username": user or "unknown",
               "args": {"filter": filter_name, "message": message}}
    try:
        async with ClientSession(timeout=ClientTimeout(total=4)) as s:
            async with s.post(url, json=payload) as r:
                if r.status >= 400:
                    print(f"[firebot] {filter_name}: HTTP {r.status}")
    except Exception as e:
        print(f"[firebot] {filter_name}: {e}")


def _fire_firebot(filter_name, user, message):
    """Fire-and-forget: trigger the Firebot preset mapped to this filter."""
    if not FB_ENABLED:
        return
    preset = FB_PRESETS.get(filter_name)
    if not preset:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_post_firebot(preset, user, message, filter_name))
    print(f"[firebot] triggered '{filter_name}' for {user or '(unknown)'}")
# -----------------------------------------------------------------------------


def apply_filters(text, user=""):
    """Normalize spammy text; return None to skip. Fires Firebot actions."""
    if F_SKIP_SPAM and _is_word_spam(text):
        _fire_firebot("word_spam", user, text)
        return None
    if F_MAX_WORD_LENGTH > 0 and any(len(w) > F_MAX_WORD_LENGTH for w in text.split()):
        _fire_firebot("long_word", user, text)
        return None
    if F_COLLAPSE_CHARS:
        collapsed = _collapse_char_runs(text)
        if collapsed != text:
            _fire_firebot("char_run", user, text)
            text = collapsed
    if F_COLLAPSE_WORDS:
        collapsed = _collapse_word_repeats(text)
        if collapsed != text:
            _fire_firebot("word_repeat", user, text)
            text = collapsed
    return text.strip() or None
# -----------------------------------------------------------------------------


def should_skip(user, text):
    if user in IGNORED_USERS:
        return True
    if text.startswith(IGNORE_PREFIXES):
        return True
    if COOLDOWN_SECONDS > 0 and user:
        now = time.monotonic()
        if now - _last_spoken.get(user, 0.0) < COOLDOWN_SECONDS:
            return True
        _last_spoken[user] = now
    if F_BLOCK_REPEATS and user:
        norm = text.strip().lower()
        if norm and _last_message.get(user) == norm:
            _fire_firebot("repeated_message", user, text)
            return True
        _last_message[user] = norm
    return False


def clean_text(text, user=""):
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)   # pocketTTS -> pocket TTS
    text = strip_custom_emotes(text)
    text = URL_RE.sub("link", text)
    text = text.strip()
    if len(text) < MIN_CHARS:
        return None
    text = apply_filters(text, user)    # optional anti-abuse filters (may skip)
    if text is None:
        return None
    text = expand_abbreviations(text)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + " ..."
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


def build_spoken(user, cleaned):
    if READ_USERNAME and user:
        return USERNAME_FORMAT.format(user=user, text=cleaned)
    return cleaned


# ------------------------------ Pocket TTS -----------------------------------
print("Loading Pocket TTS model ...")
tts_model = TTSModel.load_model(language=LANGUAGE)
print(f"Loading voice: {VOICE}")
voice_state = tts_model.get_state_for_audio_prompt(VOICE)
SAMPLE_RATE = tts_model.sample_rate
print(f"Pocket TTS ready. Mode: {MODE} | Output: {OUTPUT_DEVICE or 'default'}")

speech_queue: asyncio.Queue = asyncio.Queue()
_loop: asyncio.AbstractEventLoop | None = None  # set once main() starts; used by the tray


async def _drain_queue():
    """Drop everything queued and abort the current message. Returns count dropped."""
    dropped = 0
    while not speech_queue.empty():
        try:
            speech_queue.get_nowait()
            speech_queue.task_done()
            dropped += 1
        except asyncio.QueueEmpty:
            break
    sd.stop()
    return dropped


def speak_blocking(text):
    audio = tts_model.generate_audio(voice_state, text)
    data = np.clip(audio.numpy(), -1.0, 1.0).astype("float32")
    pad = np.zeros(int(SAMPLE_RATE * TAIL_PADDING_SECONDS), dtype="float32")
    data = np.concatenate([data, pad])
    sd.play(data, samplerate=SAMPLE_RATE, device=OUTPUT_DEVICE)
    sd.wait()


async def tts_worker():
    loop = asyncio.get_running_loop()
    while True:
        spoken = await speech_queue.get()
        try:
            await loop.run_in_executor(None, speak_blocking, spoken)
        except Exception as e:
            print(f"[TTS error] {e}")
        finally:
            speech_queue.task_done()


# ------------------------------ Mode: Twitch ---------------------------------
def parse_privmsg(line):
    tags = {}
    if line.startswith("@"):
        tag_str, _, line = line[1:].partition(" ")
        for kv in tag_str.split(";"):
            key, _, val = kv.partition("=")
            tags[key] = val
    m = PRIVMSG_RE.match(line)
    if not m:
        return None
    login = m.group(1).lower()
    message = m.group(2).rstrip("\r\n").rstrip(" \u0001")
    display = tags.get("display-name") or m.group(1)
    return login, display, message, tags.get("emotes", "")


async def chat_listener():
    import websockets
    while True:
        try:
            async with websockets.connect(TWITCH_WS, ssl=_SSL_CONTEXT) as ws:
                await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send(f"NICK justinfan{random.randint(10000, 99999)}")
                await ws.send(f"JOIN #{CHANNEL}")
                print(f"Connected to #{CHANNEL}. Waiting for messages ...")
                async for raw in ws:
                    for line in raw.split("\r\n"):
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await ws.send("PONG :tmi.twitch.tv")
                            continue
                        if "PRIVMSG" not in line:
                            continue
                        parsed = parse_privmsg(line)
                        if not parsed:
                            continue
                        login, display, message, emotes_tag = parsed
                        if should_skip(login, message):
                            continue
                        message = strip_native_emotes(message, emotes_tag)
                        cleaned = clean_text(message, login)
                        if not cleaned:
                            continue
                        print(f"{display}: {cleaned}")
                        await speech_queue.put(build_spoken(display, cleaned))
        except Exception as e:
            print(f"[Connection lost] {e} - retrying in 5 s ...")
            await asyncio.sleep(5)


# --------------------------- Control + HTTP server ---------------------------
async def run_http():
    from aiohttp import web

    async def handle_tts(request):
        if request.method == "GET":
            user = request.query.get("user", "")
            text = request.query.get("text", "")
        else:
            if request.content_type == "application/json":
                data = await request.json()
            else:
                data = await request.post()
            user = data.get("user", "")
            text = data.get("text", "")
        user = str(user).strip().lower()
        text = str(text).strip()
        if not text or should_skip(user, text):
            return web.Response(status=204)
        cleaned = clean_text(text, user)
        if not cleaned:
            return web.Response(status=204)
        print(f"[http] {cleaned}")
        await speech_queue.put(cleaned)   # speak the text as-is, no name prefix
        return web.Response(text="ok")

    async def handle_skip(request):
        # Abort the message currently being spoken; the worker advances to next.
        sd.stop()
        print("[skip] current message aborted")
        return web.Response(text="skipped")

    async def handle_clear(request):
        dropped = await _drain_queue()
        print(f"[clear] dropped {dropped} queued, aborted current")
        return web.Response(text=f"cleared {dropped}")

    @web.middleware
    async def _cors(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
        else:
            resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    app = web.Application(middlewares=[_cors])
    app.router.add_route("*", "/tts", handle_tts)
    app.router.add_route("*", "/skip", handle_skip)
    app.router.add_route("*", "/clear", handle_clear)
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    base = f"http://{HTTP_HOST}:{HTTP_PORT}"
    print(f"Control server: {base}/  (endpoints: /tts /skip /clear)")
    await asyncio.Event().wait()


async def main():
    global _loop
    _loop = asyncio.get_running_loop()
    # The control server (/skip, /clear, /tts) runs in BOTH modes so the skip
    # URL always works; twitch mode additionally reads the chat.
    if MODE == "twitch":
        await asyncio.gather(tts_worker(), run_http(), chat_listener())
    elif MODE == "http":
        await asyncio.gather(tts_worker(), run_http())
    else:
        raise SystemExit(f"Unknown mode: {MODE!r} (allowed: 'twitch', 'http')")


# ------------------------------ System tray -----------------------------------
def _subprocess_env():
    """Environment for spawning external (non-bundled) programs. A frozen
    PyInstaller app overrides LD_LIBRARY_PATH/DYLD_LIBRARY_PATH so its own
    bundled shared libs (often older than the system's) take priority for
    itself - but that leaks into any subprocess we spawn too, breaking system
    tools like xdg-open/kde-open that need the SYSTEM's newer libs (e.g.
    libstdc++). PyInstaller's bootloader stashes the pre-override value in
    *_ORIG for exactly this case."""
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            orig = env.pop(f"{var}_ORIG", None)
            if orig is not None:
                env[var] = orig
            else:
                env.pop(var, None)
    return env


def _open_path(path):
    """Open a file/folder with the OS's default handler."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], env=_subprocess_env())
        else:
            subprocess.Popen(["xdg-open", str(path)], env=_subprocess_env())
    except Exception as e:
        print(f"[tray] couldn't open {path}: {e}")


def _tray_icon_image():
    """A small equalizer-bars glyph - reads as "audio" even shrunk to 16px,
    unlike a letter which blurs into mush at tray-icon sizes."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=16, fill=(88, 101, 242, 255))
    for x, top, bottom in ((18, 24, 40), (30, 12, 52), (42, 24, 40)):
        d.rounded_rectangle((x, top, x + 6, bottom), radius=3, fill="white")
    return img


def run_tray():
    """Blocking: runs the tray icon on the calling (main) thread."""
    import pystray

    def on_open_panel(icon, item):
        _open_path(TEST_HTML_PATH)

    def on_open_config(icon, item):
        _open_path(APP_DIR)

    def on_open_log_folder(icon, item):
        _open_path(APP_DIR)

    def on_skip(icon, item):
        if _loop:
            _loop.call_soon_threadsafe(sd.stop)

    def on_clear(icon, item):
        if _loop:
            asyncio.run_coroutine_threadsafe(_drain_queue(), _loop)

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    items = [
        pystray.MenuItem(f"Twitch TTS Bot ({MODE} mode)", None, enabled=False),
        pystray.MenuItem("Open TTS panel", on_open_panel),
        pystray.MenuItem("Open config folder", on_open_config),
        pystray.MenuItem("Open log folder", on_open_log_folder),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Skip current", on_skip),
        pystray.MenuItem("Clear queue", on_clear),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    ]
    icon = pystray.Icon("twitch-tts-bot", _tray_icon_image(), "Twitch TTS Bot", pystray.Menu(*items))
    icon.run()
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    tray_available = False
    if SHOW_TRAY_ICON:
        if sys.platform not in ("win32", "darwin"):
            # Work around a pystray bug (its notify_dbus helper calls
            # gi.require_version('DBus', '1.0') for a namespace that doesn't
            # exist on any distro and is never actually used afterwards -
            # only GLib/Gio are - which otherwise kills the whole
            # AppIndicator backend with "Namespace DBus not available").
            try:
                import gi
                _orig_require_version = gi.require_version

                def _require_version(namespace, version):
                    if namespace == "DBus":
                        return
                    return _orig_require_version(namespace, version)

                gi.require_version = _require_version
            except Exception:
                pass
        try:
            import pystray  # noqa: F401
            tray_available = True
        except Exception:
            print("[tray] pystray not available, running as a plain console app:")
            import traceback
            traceback.print_exc()

    if tray_available:
        worker = threading.Thread(target=lambda: asyncio.run(main()), daemon=True)
        worker.start()
        try:
            run_tray()
        except KeyboardInterrupt:
            print("\nStopped.")
        except Exception as e:
            print(f"[tray] unavailable ({e}), continuing without it:")
            import traceback
            traceback.print_exc()
            worker.join()
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nStopped.")

# Packaging & release

This turns the bot into installers for Windows, macOS and Linux, built
automatically by GitHub Actions.

## How the release cycle works
1. Commit everything (including the `packaging/` folder and the workflow).
2. Tag a version and push it:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. GitHub Actions builds on all three OSes and attaches the results to a new
   GitHub Release:
   - Windows: `TwitchTTSBot-<ver>-Setup.exe` (Inno Setup installer, signed if
     you've added the Windows signing secrets below)
   - macOS:   `TwitchTTSBot-macos.dmg` (signed + notarized if you've added the
     Apple signing secrets below)
   - Linux:   `TwitchTTSBot-<ver>-x86_64.AppImage` (double-click, no install)
   `workflow_dispatch` lets you run a build without tagging, to test.

## What it does under the hood
- Installs **CPU-only PyTorch** (the default wheel bundles CUDA and is huge).
- Freezes the app with **PyInstaller** using `packaging/tts_bot.spec`, built
  windowless (`console=False`) since the bot runs as a **system-tray app**:
  the tray icon (via `pystray`) lets you open the config folder, open the log
  file, skip the current message, clear the queue, and quit. Set
  `"show_tray_icon": false` in `config.json` to run as a plain console app
  instead; it also falls back to console mode automatically if the tray
  backend can't start (e.g. headless Linux with no display).
- Since there's no console window, all `print()` output goes to a log file
  instead: `tts_bot.log` next to `config.json` in the per-user folder below.
- On first run the app copies `config.json` / `abbreviations.json` /
  `emotes.json` into a per-user folder so they stay editable:
  - Windows `%APPDATA%\twitch-tts-bot`
  - macOS   `~/Library/Application Support/twitch-tts-bot`
  - Linux   `~/.config/twitch-tts-bot`

## Code signing / notarization (optional, off by default)
The workflow signs and notarizes automatically once you add these as **repo
secrets** (Settings -> Secrets and variables -> Actions). Leave them unset and
the build still works, just unsigned/unnotarized as before.

- **Windows** (needs an OV/EV code-signing certificate):
  - `WINDOWS_CERTIFICATE_BASE64` - your `.pfx` file, base64-encoded
    (`base64 -w0 cert.pfx`)
  - `WINDOWS_CERTIFICATE_PASSWORD` - its password
- **macOS** (needs an Apple Developer account, $99/yr):
  - `MACOS_CERTIFICATE_BASE64` - your "Developer ID Application" `.p12`,
    base64-encoded (`base64 -i cert.p12 | tr -d '\n'`)
  - `MACOS_CERTIFICATE_PASSWORD` - its password
  - `MACOS_CERTIFICATE_IDENTITY` - the signing identity string, e.g.
    `Developer ID Application: Your Name (TEAMID1234)`
  - `APPLE_ID` - your Apple ID email
  - `APPLE_ID_PASSWORD` - an **app-specific password** (generate one at
    appleid.apple.com), not your real Apple ID password
  - `APPLE_TEAM_ID` - your 10-character Apple Developer Team ID

Without these: Windows SmartScreen will warn ("More info -> Run anyway") and
macOS Gatekeeper will block the unsigned `.app` ("right-click -> Open" works
around it).

## Honest caveats (read before promising anyone a smooth install)
- **Size.** PyTorch makes each build ~0.7–1.5 GB. That is inherent to the model
  stack, not a bug. The model itself still downloads on first run (needs
  internet once), then runs offline.
- **The AppImage and tray icon are placeholders visually** - both use a
  generated colored-circle icon, not real artwork. Swap `_tray_icon_image()`
  in `tts_bot.py` and the icon-drawing step in the workflow for real assets
  whenever you have them.
- **pystray's Linux backend** needs either `python-xlib` (installed
  automatically via pip on Linux, works under X11/XWayland) or a
  system-installed AppIndicator (`gi`/`AppIndicator3`, not pip-installable).
  On a pure-Wayland session without XWayland, the tray icon may not appear;
  the bot still runs fine as a console app in that case (or set
  `"show_tray_icon": false`).
- **Virtual audio device can't be bundled.** BlackHole (macOS) and VB-CABLE
  (Windows) are drivers the user installs themselves; the installer only links
  to them. On Linux, OBS "Application Audio Capture" avoids needing one.
- **First green build takes iteration.** PyInstaller + PyTorch usually needs a
  couple of tweaks (a missing hidden import, a data file). Use
  `workflow_dispatch`, read the log, adjust `tts_bot.spec`, repeat. This is
  normal, not a sign anything is broken.
- **Action versions** (checkout@v4, setup-python@v5, upload-artifact@v4,
  action-gh-release@v2) are current at time of writing; bump if CI complains.
- **appimagetool** is downloaded from AppImageKit's `continuous` GitHub
  release at build time; if that URL ever moves, the Linux job needs its
  download line updated.

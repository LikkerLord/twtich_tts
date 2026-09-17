; Inno Setup script -> builds TwitchTTSBot-<version>-Setup.exe
; Version is passed by CI:  ISCC /DAppVersion=1.2.3 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=Twitch TTS Bot
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Twitch TTS Bot
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
SourceDir=..\..
OutputDir=Output
OutputBaseFilename=TwitchTTSBot-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\tts-bot\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Twitch TTS Bot"; Filename: "{app}\tts-bot.exe"
Name: "{autodesktop}\Twitch TTS Bot"; Filename: "{app}\tts-bot.exe"

[Run]
Filename: "{app}\tts-bot.exe"; Description: "Launch now"; Flags: nowait postinstall skipifsilent

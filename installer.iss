; WavTube mp3+ installer script (Inno Setup 6)
; Compiled automatically by build_installer.bat. Manual build: ISCC.exe installer.iss
; NOTE: keep this file ASCII-only (no BOM -> Inno reads it as ANSI).

#ifndef MyAppVersion
  #define MyAppVersion "0.6"
#endif
#define MyAppName "WavTube mp3+"
#define MyAppExe "WavTube.exe"

[Setup]
; AppId must stay fixed. Changing it makes upgrades install side-by-side as a different app.
AppId={{BD79967B-7C60-4EDC-915B-902B3338B580}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=suzuya
AppPublisherURL=https://instagram.com/suzuya_ins
DefaultDirName={autopf}\WavTube
DisableProgramGroupPage=yes
; Per-user install by default (no admin needed). 'All users' can be chosen in the setup dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=WavTube_Setup_{#MyAppVersion}
SetupIconFile=WavTube.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller (onedir) output
Source: "dist\WavTube\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; ffmpeg/ffprobe are placed next to the exe instead of being embedded (faster startup)
Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion
; Deno = JavaScript runtime required by yt-dlp for YouTube (fetched by build_installer.py)
Source: "deno.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[InstallDelete]
; Clean old bundled files when upgrading in place
Type: filesandordirs; Name: "{app}\_internal"
; Drop yt-dlp fetched by in-app update so the freshly bundled version takes effect
Type: filesandordirs; Name: "{localappdata}\WavTube_mp3_plus\lib"
Type: filesandordirs; Name: "{localappdata}\WavTube_mp3_plus\lib.broken"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\WavTube_mp3_plus\lib"
Type: filesandordirs; Name: "{localappdata}\WavTube_mp3_plus\lib.broken"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

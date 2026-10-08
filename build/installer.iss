; Inno Setup script for Voice Typing. Compiled by build\build_exe.ps1 after PyInstaller.
; Per-user install (no admin prompt) into %LOCALAPPDATA%\Programs\Voice Typing.

#define AppName "Voice Typing"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "Voice Typing.exe"
#define SourceDir "..\dist\Voice Typing"

[Setup]
AppId={{B8D3C0E1-2C8E-4D6A-9C57-6F1E6B8E3A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=James Beadle
AppPublisherURL=https://github.com/grungenut/voice-typing
AppSupportURL=https://github.com/grungenut/voice-typing
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=VoiceTyping-Setup-{#AppVersion}
SetupIconFile=..\assets\voice_typing.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
InfoBeforeFile=..\build\installer-notes.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start {#AppName} when I sign in to Windows"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; PyInstaller keeps its copies under _internal\; put readable copies at the top level too.
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Hold Right Alt to dictate, tap Right Ctrl to record a meeting"
Name: "{group}\{#AppName} settings"; Filename: "notepad.exe"; Parameters: """{localappdata}\VoiceTyping\settings.ini"""; Comment: "Edit the settings file"
Name: "{group}\Third-party notices"; Filename: "{app}\THIRD-PARTY-NOTICES.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#AppName}"; Flags: deletevalue; Tasks: not startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#AppExe}"""; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\VoiceTyping\voice_typing.log"

[Code]
// Stop a running copy before installing over it.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

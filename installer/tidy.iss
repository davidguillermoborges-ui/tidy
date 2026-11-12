; Tidy installer (Inno Setup 6). Built by .github/workflows/build.yml:
;   iscc /DAppVersion=1.2.0 installer\tidy.iss   ->  dist\TidySetup-1.2.0.exe
; Installs for the current Windows user only (no admin password), next to where HMNS Dev puts it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2B71-6D4E-4A9B-9C55-1E7A0D2F4B10}
AppName=Tidy
AppVersion={#AppVersion}
AppVerName=Tidy {#AppVersion}
AppPublisher=HMNS
AppPublisherURL=https://github.com/davidguillermoborges-ui/tidy
AppSupportURL=https://github.com/davidguillermoborges-ui/tidy/issues
AppUpdatesURL=https://github.com/davidguillermoborges-ui/tidy/releases
DefaultDirName={localappdata}\Programs\Tidy
DisableDirPage=yes
DisableProgramGroupPage=yes
DefaultGroupName=Tidy
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TidySetup-{#AppVersion}
SetupIconFile=..\assets\tidy.ico
UninstallDisplayIcon={app}\Tidy.exe
UninstallDisplayName=Tidy
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no

[Tasks]
Name: "connect"; Description: "Connect Tidy to Claude Desktop now"; GroupDescription: "Claude:"
Name: "desktopicon"; Description: "Put a Tidy shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Tidy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Tidy"; Filename: "{app}\Tidy.exe"
Name: "{userdesktop}\Tidy"; Filename: "{app}\Tidy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Tidy.exe"; Parameters: "--connect"; Tasks: connect; Flags: runhidden waituntilterminated; StatusMsg: "Connecting Tidy to Claude..."
Filename: "{app}\Tidy.exe"; Description: "Open Tidy"; Flags: postinstall nowait skipifsilent
; "Update now" in Tidy's Settings runs this installer with /SILENT /relaunch=1: open Tidy again afterwards
Filename: "{app}\Tidy.exe"; Flags: nowait; Check: Relaunch

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Tidy.exe"; Flags: runhidden; RunOnceId: "StopTidy"
Filename: "{app}\Tidy.exe"; Parameters: "--disconnect"; Flags: runhidden waituntilterminated; RunOnceId: "Disconnect"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM tidy-server.exe"; Flags: runhidden; RunOnceId: "StopServer"

[Messages]
FinishedLabel=Tidy is installed.%n%nIf Claude Desktop is open, quit it fully (right-click its icon by the clock and choose Quit), then open it again.%n%nThen type "tidy" and a folder in Claude, for example: tidy my Downloads folder.

[Code]
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;

// Stop a running Tidy window and Tidy's Claude connection so their files can be replaced on an update.
// Claude reconnects to Tidy the next time it starts.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Tidy.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM tidy-server.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(500);
  Result := '';
end;

[Setup]
AppName=Horizon Video Downloader
AppVersion=5.2
DefaultDirName={autopf}\HorizonDownloader
DefaultGroupName=Horizon Video Downloader
OutputDir=.
OutputBaseFilename=HorizonDownloader_Setup_v5.2
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
CloseApplications=no
RestartApplications=no
SetupIconFile=icon.ico

[Files]
Source: "dist_v52\HorizonDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "cookies.txt"; DestDir: "{app}"; Flags: ignoreversion; Check: FileExists('cookies.txt')
Source: "cookies.txt"; DestDir: "{app}\_internal"; Flags: ignoreversion; Check: FileExists('cookies.txt')

[Icons]
Name: "{autodesktop}\Horizon Video Downloader"; Filename: "{app}\HorizonDownloader.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autoprograms}\Horizon Video Downloader"; Filename: "{app}\HorizonDownloader.exe"; WorkingDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\HorizonDownloader.exe"; Description: "Launch Horizon Video Downloader"; Flags: nowait postinstall skipifsilent

[Code]
procedure KillRunningProcesses();
var
  ResultCode: Integer;
begin
  // Force terminate any lingering Horizon Downloader or download tools using cmd.exe
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM HorizonDownloader.exe /IM yt-dlp.exe /IM ffmpeg.exe /IM ffprobe.exe /IM gallery-dl.exe /IM deno.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // Also invoke taskkill directly from System directory
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM HorizonDownloader.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM yt-dlp.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM ffmpeg.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM ffprobe.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM gallery-dl.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM deno.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // Sleep 800ms so Windows kernel releases file locks
  Sleep(800);
end;

function InitializeSetup(): Boolean;
begin
  KillRunningProcesses();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillRunningProcesses();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    KillRunningProcesses();
  end;
  if CurStep = ssPostInstall then
  begin
    Exec(ExpandConstant('{cmd}'), '/C findstr /i "hvd.com" "' + ExpandConstant('{sys}\drivers\etc\hosts') + '" >nul || (echo.>> "' + ExpandConstant('{sys}\drivers\etc\hosts') + '" & echo 127.0.0.1 hvd.com>> "' + ExpandConstant('{sys}\drivers\etc\hosts') + '" & echo 127.0.0.1 www.hvd.com>> "' + ExpandConstant('{sys}\drivers\etc\hosts') + '" & ipconfig /flushdns >nul)', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

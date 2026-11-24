; Barrens Voice's installer (Inno Setup 6): `mise run installer` builds it on Windows (tools/installer.py).
; Small by design: uv.exe, bv/install.py and the release archive. What is large comes from the network
; while installing: Python and the libraries through uv (from uv.lock), the models (bv --fetch-models). Then the
; addon into the games found, those the player ticks (the page «Аддон в игры», [Code]).
; Layout and updates: docs/update-strategy.md.

#ifndef AppVersion
  #error Pass /DAppVersion=<version> (tools/installer.py does)
#endif

[Setup]
AppId={{6F2E1C55-3B8D-4E57-9C61-0B6E2A7D4F19}
AppName=Barrens Voice
AppVersion={#AppVersion}
AppPublisher=rgeraskin
AppPublisherURL=https://github.com/rgeraskin/barrens-voice
AppSupportURL=https://github.com/rgeraskin/barrens-voice/issues
DefaultDirName={localappdata}\BarrensVoice
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; Off: RedirectionGuard (on by default) is inherited by what [Run] starts, runasoriginaluser or not when Setup
; is not elevated, and the install is made of junctions - uv's Python (cpython-3.13 -> 3.13.x) and our
; app\current: traversing them failed with «untrusted mount point» (error 448). The guard protects elevated
; installers from junctions planted by a lesser user; this one runs as that same user in that user's folder.
RedirectionGuard=no
OutputDir=..\dist
; one name for every version: README links releases/latest/download/BarrensVoice-Setup.exe (the version is the release's)
OutputBaseFilename=BarrensVoice-Setup
SetupIconFile=..\companion\bv\launcher\icon.ico
UninstallDisplayIcon={app}\Barrens Voice.exe
UninstallDisplayName=Barrens Voice
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
; what the libraries and the models take after installing (README: about 6 GB with NVIDIA)
ExtraDiskSpaceRequired=6442450944
; Setup and Uninstall wait while the launcher or the companion runs (their named mutexes, bv/launcher/app.py
; and bv/__main__.py, "Local\": this session's): installing over a running version fails in uv sync or the switch
AppMutex=BarrensVoiceLauncher,BarrensVoiceCompanion
; the steps' output (uv's, the program's) goes into Setup's log (%TEMP%\Setup Log <date> #NNN.txt), named on a failure
SetupLogging=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ru.SelectDirLabel3=Barrens Voice установится в эту папку вместе со всем, что скачает: библиотеками и моделями (около 6 ГБ с видеокартой NVIDIA, около 4 ГБ с другой).

[Tasks]
Name: "desktopicon"; Description: "Значок на рабочем столе"

[Files]
Source: "..\dist\uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\companion\bv\install.py"; DestDir: "{app}\setup"; Flags: ignoreversion
; the starter a player finds in the folder, with the app's icon; the shortcuts and the sign-in go through it
Source: "..\dist\Barrens Voice.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\barrens-voice-{#AppVersion}.zip"; DestDir: "{app}\setup"; Flags: ignoreversion

[Run]
; Python, the libraries and the models are the steps in [Code] (CurStepChanged): each under its name on the page,
; the line it is at below it, again on a failure. The launcher: when the program's step went through
Filename: "{app}\Barrens Voice.exe"; WorkingDir: "{app}"; Description: "Запустить Barrens Voice Launcher"; Flags: postinstall nowait skipifsilent; Check: SetupDone

[Icons]
Name: "{userprograms}\Barrens Voice"; Filename: "{app}\Barrens Voice.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Barrens Voice"; Filename: "{app}\Barrens Voice.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; the launcher's «Запускать при входе в Windows» writes this value: gone with the program
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Barrens Voice"; Flags: uninsdeletevalue dontcreatekey

[UninstallRun]
; Uninstall does not start while the launcher or the companion holds its mutex (AppMutex above: it asks to close
; Barrens Voice): this stops only what is left of this install without one - the launcher and the companion of
; this install, not other Python programs. StartsWith, not -like: "[" in a folder name is a wildcard there; the
; folder's "'" doubled for PowerShell's quotes (AppForPowerShell). Inno
; reads "{{" as "{" and leaves "}" as it is (its help, "Constants": "You do not need to double } characters")
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""$app = '{code:AppForPowerShell}\'; Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith($app, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopBarrensVoice"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\setup"
Type: files; Name: "{app}\barrens-voice.install"

[Code]
{ The page «Аддон в игры», after installing: the games the program just installed finds (bv --find-games, as the
  launcher finds them: launcher.model.setup_games), a box each, all ticked; Next puts the addon into the ticked ones
  (bv --install-addon <game>). Nothing found, or a silent install: no page (the launcher offers the addon too). }
var
  GamesPage: TInputOptionWizardPage;
  GameKeys: TArrayOfString;
  GamesLooked: Boolean;

procedure InitializeWizard;
begin
  GamesPage := CreateInputOptionPage(wpInfoAfter, 'Аддон в игры', 'Куда поставить аддон Barrens Voice',
    'Отметь игры, в которые поставить аддон. Можно и потом: «установить аддон» в лаунчере.', False, False);
end;

function AppPython: String;
begin
  Result := ExpandConstant('{app}\app\current\.venv\Scripts\python.exe');
end;

function AppCompanion: String;
begin
  Result := ExpandConstant('{app}\app\current\companion');
end;

{ The steps after the files: Python and the libraries (uv's Python runs install.py, which builds app\<version> from
  its uv.lock), then the models (bv --fetch-models: now, not at the first start). Each one's name on the page, the
  last line of its output below it (uv's and the program's; all of it in Setup's log); a step that fails asks to go
  again (what is downloaded stays in the cache). The program's step not done: no addon page, no launcher; the models'
  not done: the program downloads them at its first start. A «BV_NOTICE: » line (install.py: why DirectML on an
  NVIDIA card) is shown after the steps. }
var
  SetupFailed, DriverToUpdate: Boolean;
  Notices, LastLine, OldDriver: String;
  LastCode: Integer;

function SetEnvironmentVariable(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function SetupDone: Boolean;
begin
  Result := not SetupFailed;
end;

procedure StepOutput(const S: String; const Error, FirstLine: Boolean);
begin
  Log(S);
  if Pos('BV_NOTICE: ', S) = 1 then
    Notices := Notices + Copy(S, 12, Length(S)) + #13#10#13#10
  else if Pos('BV_DRIVER: ', S) = 1 then
    OldDriver := Copy(S, 12, Length(S))
  else if Trim(S) <> '' then
  begin
    LastLine := Trim(S);
    WizardForm.FilenameLabel.Caption := LastLine;
  end;
end;

function RunStep(const Name, Filename, Params, Dir: String): Boolean;
var
  ResultCode: Integer;
  Before: String;
begin
  Before := Notices;
  repeat
    Notices := Before;                  { the step's notices once, however many times it is run }
    OldDriver := '';
    WizardForm.StatusLabel.Caption := Name;
    WizardForm.FilenameLabel.Caption := '';
    LastLine := '';
    if ExecAndLogOutput(Filename, Params, Dir, SW_HIDE, ewWaitUntilTerminated, ResultCode, @StepOutput) then
      Result := ResultCode = 0
    else
    begin
      Result := False;                  { did not start at all: Windows' reason }
      LastLine := SysErrorMessage(ResultCode);
    end;
    LastCode := ResultCode;
  { install.py's 3 with its BV_DRIVER line: the NVIDIA driver is too old for CUDA - asked about by the caller, not
    «again» (3 alone is also Windows' «path not found» for a program that did not start) }
  until Result or WizardSilent or ((LastCode = 3) and (OldDriver <> '')) or
        (SuppressibleMsgBox(Name + #13#10#13#10 + 'Не получилось: ' + LastLine + #13#10#13#10 +
                            'Повторить? Скачанное заново не скачивается.' + #13#10 + 'Журнал установки: ' +
                            ExpandConstant('{log}'), mbError, MB_RETRYCANCEL, IDCANCEL) <> IDRETRY);
end;

{ the last page after the program's step failed: not Inno's «установлена» }
function FailedText: String;
begin
  if DriverToUpdate then
    Result := 'Barrens Voice не установлен: сначала обнови драйвер NVIDIA (страница драйверов открыта в браузере), ' +
              'потом запусти установщик ещё раз — скачанное возьмётся из кэша.'
  else
    Result := 'Barrens Voice установлен не до конца: Python и библиотеки не скачались. Запусти установщик ещё раз — ' +
              'скачанное возьмётся из кэша.';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and SetupFailed then
  begin
    WizardForm.FinishedLabel.Caption := FailedText;
    WizardForm.FinishedLabel.AdjustHeight;    { as Inno does for its own text: the label as tall as the text }
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  App, Name, Params: String;
  Code: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  App := ExpandConstant('{app}');
  SetEnvironmentVariable('UV_PYTHON_INSTALL_DIR', App + '\python');
  SetEnvironmentVariable('UV_CACHE_DIR', App + '\cache\uv');
  SetEnvironmentVariable('UV_PYTHON_PREFERENCE', 'only-managed');
  { Python's output in UTF-8, as Inno reads it (else the code page's: the Cyrillic lost) }
  SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8');
  WizardForm.ProgressGauge.Style := npbstMarquee;
  Name := 'Скачиваю Python и библиотеки (0,6–2,5 ГБ, несколько минут)…';
  Params := 'run --no-project --python 3.13 "' + App + '\setup\install.py" --root "' + App + '" --archive "' + App +
    '\setup\barrens-voice-{#AppVersion}.zip"';
  SetupFailed := not RunStep(Name, App + '\uv.exe', Params, App);
  { the NVIDIA driver too old for CUDA (install.py stopped before any library): update it - the best the mod gets,
    the default - or go on without CUDA (DirectML: the game may stutter while a line is made); a silent install goes on }
  if SetupFailed and (LastCode = 3) and (OldDriver <> '') then
  begin
    if not WizardSilent and (SuppressibleMsgBox(OldDriver + #13#10#13#10 + 'Обновить драйвер NVIDIA?' + #13#10#13#10 +
                          'Да — откроется страница драйверов NVIDIA, установка остановится. Обнови драйвер и запусти ' +
                          'установщик ещё раз.' + #13#10#13#10 + 'Нет — поставлю без CUDA: голоса рас будут, но игра ' +
                          'может подтормаживать, пока готовится строка.', mbConfirmation, MB_YESNO, IDNO) = IDYES) then
    begin
      DriverToUpdate := True;
      ShellExec('open', 'https://www.nvidia.com/Download/index.aspx', '', '', SW_SHOWNORMAL, ewNoWait, Code);
    end
    else
      SetupFailed := not RunStep(Name, App + '\uv.exe', Params + ' --runtime directml', App);
  end;
  if not SetupFailed and not RunStep('Скачиваю модели голосов (около 3 ГБ)…', AppPython, '-m bv --fetch-models',
                                     AppCompanion) then
    Notices := Notices + 'Модели голосов не скачались: программа скачает их при первом запуске.' + #13#10#13#10;
  WizardForm.ProgressGauge.Style := npbstNormal;
  WizardForm.FilenameLabel.Caption := '';
  if SetupFailed and not DriverToUpdate then
    SuppressibleMsgBox(FailedText + #13#10 + 'Журнал установки: ' + ExpandConstant('{log}'), mbError, MB_OK, IDOK)
  else if Notices <> '' then
    SuppressibleMsgBox(Trim(Notices), mbInformation, MB_OK, IDOK);
end;

{ the lines of bv --find-games: key, tab, what the box says }
procedure FindGames;
var
  List, Line, Key: String;
  Lines: TArrayOfString;
  I, Tab, ResultCode: Integer;
begin
  GamesLooked := True;
  List := ExpandConstant('{tmp}\bv-games.txt');
  if not Exec(AppPython, '-m bv --find-games "' + List + '"', AppCompanion, SW_HIDE, ewWaitUntilTerminated,
              ResultCode) or (ResultCode <> 0) or not LoadStringsFromFile(List, Lines) then
    Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Lines[I];
    Tab := Pos(#9, Line);
    if Tab = 0 then
      Continue;
    Key := Copy(Line, 1, Tab - 1);
    Delete(Line, 1, Tab);
    SetArrayLength(GameKeys, GetArrayLength(GameKeys) + 1);
    GameKeys[GetArrayLength(GameKeys) - 1] := Key;
    GamesPage.Values[GamesPage.Add(Line)] := True;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = GamesPage.ID then
  begin
    if WizardSilent or SetupFailed then
    begin
      Result := True;
      Exit;
    end;
    if not GamesLooked then
      FindGames;
    Result := GetArrayLength(GameKeys) = 0;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Failed: String;
  I, ResultCode: Integer;
begin
  Result := True;
  if CurPageID <> GamesPage.ID then
    Exit;
  Failed := '';
  for I := 0 to GetArrayLength(GameKeys) - 1 do
    if GamesPage.Values[I] then
      if not Exec(AppPython, '-m bv --install-addon ' + GameKeys[I], AppCompanion, SW_HIDE, ewWaitUntilTerminated,
                  ResultCode) or (ResultCode <> 0) then
        Failed := Failed + #13#10 + GamesPage.CheckListBox.ItemCaption[I];
  if Failed <> '' then
    MsgBox('Аддон не поставился:' + Failed + #13#10#13#10 +
           'Поставь его из лаунчера: «установить аддон». Почему не вышло — в журнале программы (data\logs).',
           mbError, MB_OK);
end;

{ the install folder inside PowerShell's single quotes: a ' in it doubled }
function AppForPowerShell(Param: String): String;
begin
  Result := ExpandConstant('{app}');
  StringChangeEx(Result, '''', '''''', True);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Удалить и настройки, банк голосов и скачанные модели (около 3 ГБ)?' + #13#10 +
              'Нет — они останутся и пригодятся, если поставить Barrens Voice снова.',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      DelTree(ExpandConstant('{app}\cache'), True, True, True);
      RemoveDir(ExpandConstant('{app}'));
    end;
end;

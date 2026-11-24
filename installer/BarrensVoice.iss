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
; Python and the libraries: uv's own Python runs install.py, which builds app\{#AppVersion} from its uv.lock.
; set "VAR=value": the folder quoted, so a "&" in it does not end the command
Filename: "{cmd}"; Parameters: "/c ""set ""UV_PYTHON_INSTALL_DIR={app}\python""&& set ""UV_CACHE_DIR={app}\cache\uv""&& set ""UV_PYTHON_PREFERENCE=only-managed""&& ""{app}\uv.exe"" run --no-project --python 3.13 ""{app}\setup\install.py"" --root ""{app}"" --archive ""{app}\setup\barrens-voice-{#AppVersion}.zip"" || pause"""; StatusMsg: "Скачиваю Python и библиотеки (0,6–2,5 ГБ, несколько минут)…"; Flags: waituntilterminated
; the models now, not at the first start (~3 GB once)
Filename: "{app}\app\current\.venv\Scripts\python.exe"; Parameters: "-m bv --fetch-models"; WorkingDir: "{app}\app\current\companion"; StatusMsg: "Скачиваю модели голосов (около 3 ГБ)…"; Flags: waituntilterminated
Filename: "{app}\Barrens Voice.exe"; WorkingDir: "{app}"; Description: "Запустить Barrens Voice Launcher"; Flags: postinstall nowait skipifsilent

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
    if WizardSilent then
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

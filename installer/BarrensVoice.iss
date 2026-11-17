; Barrens Voice's installer (Inno Setup 6): `mise run installer` builds it on Windows (tools/installer.py).
; Small by design: uv.exe, bv/install.py and the release archive. What is large comes from the network
; while installing: Python and the libraries through uv (from uv.lock), the models (bv --fetch-models).
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
OutputBaseFilename=BarrensVoice-Setup-{#AppVersion}
SetupIconFile=..\companion\bv\launcher\icon.ico
UninstallDisplayIcon={app}\app\current\companion\bv\launcher\icon.ico
UninstallDisplayName=Barrens Voice
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
; what the libraries and the models take after installing (README: about 6 GB with NVIDIA)
ExtraDiskSpaceRequired=6442450944

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ru.SelectDirLabel3=Barrens Voice установится в эту папку вместе со всем, что скачает: библиотеками и моделями (около 6 ГБ с видеокартой NVIDIA, около 4 ГБ с другой).

[Tasks]
Name: "desktopicon"; Description: "Значок на рабочем столе"

[Files]
Source: "..\dist\uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\companion\bv\install.py"; DestDir: "{app}\setup"; Flags: ignoreversion
Source: "..\dist\barrens-voice-{#AppVersion}.zip"; DestDir: "{app}\setup"; Flags: ignoreversion

[Run]
; Python and the libraries: uv's own Python runs install.py, which builds app\{#AppVersion} from its uv.lock
Filename: "{cmd}"; Parameters: "/c ""set UV_PYTHON_INSTALL_DIR={app}\python&& set UV_CACHE_DIR={app}\cache\uv&& set UV_PYTHON_PREFERENCE=only-managed&& ""{app}\uv.exe"" run --no-project --python 3.13 ""{app}\setup\install.py"" --root ""{app}"" --archive ""{app}\setup\barrens-voice-{#AppVersion}.zip"" || pause"""; StatusMsg: "Скачиваю Python и библиотеки (0,6–2,5 ГБ, несколько минут)…"; Flags: waituntilterminated
; the models now, not at the first start (~3 GB once)
Filename: "{app}\app\current\.venv\Scripts\python.exe"; Parameters: "-m bv --fetch-models"; WorkingDir: "{app}\app\current\companion"; StatusMsg: "Скачиваю модели голосов (около 3 ГБ)…"; Flags: waituntilterminated
Filename: "{app}\app\current\.venv\Scripts\pythonw.exe"; Parameters: """{app}\app\current\companion\BarrensVoice.pyw"""; WorkingDir: "{app}\app\current\companion"; Description: "Запустить Barrens Voice"; Flags: postinstall nowait skipifsilent

[Icons]
Name: "{userprograms}\Barrens Voice"; Filename: "{app}\app\current\.venv\Scripts\pythonw.exe"; Parameters: """{app}\app\current\companion\BarrensVoice.pyw"""; WorkingDir: "{app}\app\current\companion"; IconFilename: "{app}\app\current\companion\bv\launcher\icon.ico"
Name: "{userdesktop}\Barrens Voice"; Filename: "{app}\app\current\.venv\Scripts\pythonw.exe"; Parameters: """{app}\app\current\companion\BarrensVoice.pyw"""; WorkingDir: "{app}\app\current\companion"; IconFilename: "{app}\app\current\companion\bv\launcher\icon.ico"; Tasks: desktopicon

[Registry]
; the launcher's «Запускать при входе в Windows» writes this value: gone with the program
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Barrens Voice"; Flags: uninsdeletevalue dontcreatekey

[UninstallRun]
; the launcher and the companion of this install, not other Python programs
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -like '{app}\*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"""; Flags: runhidden; RunOnceId: "StopBarrensVoice"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\setup"
Type: files; Name: "{app}\barrens-voice.install"

[Code]
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

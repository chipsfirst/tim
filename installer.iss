[Setup]
AppName=Т.И.М.
AppVersion=0.7.1
DefaultDirName={autopf}\TIM
DefaultGroupName=Т.И.М.
OutputDir=dist
OutputBaseFilename=TIM-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\TIM.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\TIM\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Т.И.М."; Filename: "{app}\TIM.exe"
Name: "{autodesktop}\Т.И.М."; Filename: "{app}\TIM.exe"

[Run]
Filename: "{app}\TIM.exe"; Description: "Запустить Т.И.М."; Flags: nowait postinstall skipifsilent

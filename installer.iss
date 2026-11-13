; Inno Setup 安装向导脚本 - 生成 Windows 双击即装的 EblanaDeskPet_Setup.exe
#define MyAppName "死芒桌宠"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Victorgreatmarshal"
#define MyAppExeName "EblanaDeskPet.exe"

[Setup]
AppId={{8E4C5E7B-9A2D-4F1E-B8C0-450NECRAS2025}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EblanaDeskPet
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=EblanaDeskPet_Setup
SetupIconFile=assets\official\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\EblanaDeskPet\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\EblanaDeskPet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动死芒桌宠"; Flags: nowait postinstall skipifsilent

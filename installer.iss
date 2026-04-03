; Скрипт Inno Setup для создания установщика ChemTG Bot
[Setup]
AppName=ChemTG Bot
AppVersion=1.0
DefaultDirName={autopf}\ChemTG_Bot
DefaultGroupName=ChemTG Bot
OutputDir=Output
OutputBaseFilename=ChemTG_Bot_Installer
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
; Опционально: Иконка для установщика
; SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ChemTG_Bot.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Основной исполняемый файл (собранный PyInstaller)
Source: "dist\ChemTG_Bot.exe"; DestDir: "{app}"; Flags: ignoreversion

; Конфигурационный файл
Source: "config.yaml"; DestDir: "{app}"; Flags: ignoreversion

; .env файл с ключами
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion

; Все файлы из папки bin
Source: "bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Создаем пустые папки, которые требует бот
Name: "{app}\data"
Name: "{app}\data\vpn"
Name: "{app}\bin"
Name: "{app}\logs"

[Icons]
; Ярлыки
Name: "{group}\ChemTG Bot"; Filename: "{app}\ChemTG_Bot.exe"
Name: "{autodesktop}\ChemTG Bot"; Filename: "{app}\ChemTG_Bot.exe"; Tasks: desktopicon

[Run]
; Запуск после установки
Filename: "{app}\ChemTG_Bot.exe"; Description: "{cm:LaunchProgram,ChemTG Bot}"; Flags: nowait postinstall skipifsilent

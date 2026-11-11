; Installer Windows ClixMax (Inno Setup 6). Dikompilasi oleh packaging/build.py, yang mengisi AppVersion,
; NumericVersion, SourceDir, OutputDir, OutputName, dan IconFile.
;
; Dipasang per pengguna di %LOCALAPPDATA%\Programs\ClixMax, jadi tidak perlu izin administrator. Data pengguna
; (%APPDATA%\clixmax) tidak disentuh saat memperbarui maupun menghapus.

[Setup]
AppId={{6F1C3B52-8E4D-4A7B-9D2E-5C0A7B3E9F14}
AppName=ClixMax
AppVersion={#AppVersion}
AppVerName=ClixMax {#AppVersion}
AppPublisher=ClixMax
AppPublisherURL=https://github.com/taufikmaulidi/clixmax-music
VersionInfoVersion={#NumericVersion}
DefaultDirName={autopf}\ClixMax
DefaultGroupName=ClixMax
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Langsung pasang: tanpa halaman folder, grup Start Menu, dan ringkasan.
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
WizardStyle=modern
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\ClixMax.exe
UninstallDisplayName=ClixMax
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/max
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Isi versi lama dibuang dulu supaya berkas yang sudah tidak dipakai tidak tertinggal.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\bin"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID sama dengan yang dipasang ClixMax (system.prepare_process), supaya ikon taskbar dan panel media
; Windows mengenalinya sebagai ClixMax.
Name: "{autoprograms}\ClixMax"; Filename: "{app}\ClixMax.exe"; AppUserModelID: "clixmax.player"
Name: "{autodesktop}\ClixMax"; Filename: "{app}\ClixMax.exe"; AppUserModelID: "clixmax.player"; Tasks: desktopicon

[Run]
Filename: "{app}\ClixMax.exe"; Description: "{cm:LaunchProgram,ClixMax}"; Flags: nowait postinstall skipifsilent

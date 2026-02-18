#define MySource GetStringParam('MySource')

[Setup]
AppName=Patakha
AppVersion=0.1.0
DefaultDirName={pf}\Patakha
DefaultGroupName=Patakha
OutputDir={#MySource}\..
OutputBaseFilename=Patakha-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#MySource}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Patakha Studio"; Filename: "{app}\run_studio.bat"
Name: "{group}\Patakha CLI"; Filename: "{app}\run_patakha.bat"
Name: "{group}\Uninstall Patakha"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\run_studio.bat"; Description: "Launch Patakha Studio"; Flags: postinstall nowait skipifsilent

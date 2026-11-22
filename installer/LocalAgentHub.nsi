Unicode true
!include "MUI2.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif
!define APP_NAME "Local Agent Hub"
!define PRODUCT_KEY "Software\LocalAgentHub"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Local Agent Hub"

Name "${APP_NAME} ${APP_VERSION}"
Caption "${APP_NAME} 安装程序"
OutFile "../dist/Local-Agent-Hub-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\Local Agent Hub"
InstallDirRegKey HKCU "${PRODUCT_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APP_NAME} Windows Installer"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "OriginalFilename" "Local-Agent-Hub-Setup-${APP_VERSION}.exe"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\launch-installed.bat"
!define MUI_FINISHPAGE_RUN_TEXT "安装完成后启动 Local Agent Hub"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Local Agent Hub" MainSection
  SectionIn RO
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File "..\main.py"
  File "..\requirements.txt"
  File "..\run_windows.bat"
  File "launch-installed.bat"
  File "..\config.example.json"
  File "..\README.md"

  SetOutPath "$INSTDIR\static"
  File "..\static\index.html"
  File "..\static\app.css"
  File "..\static\app.js"

  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\Local Agent Hub"
  CreateShortcut "$SMPROGRAMS\Local Agent Hub\Local Agent Hub.lnk" "$INSTDIR\launch-installed.bat" "" "$SYSDIR\shell32.dll" 44 SW_SHOWNORMAL "" "启动 Local Agent Hub"
  CreateShortcut "$SMPROGRAMS\Local Agent Hub\卸载 Local Agent Hub.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${PRODUCT_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Local Agent Hub"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\Uninstall.exe,0"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\Local Agent Hub\Local Agent Hub.lnk"
  Delete "$SMPROGRAMS\Local Agent Hub\卸载 Local Agent Hub.lnk"
  RMDir "$SMPROGRAMS\Local Agent Hub"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  DeleteRegKey HKCU "${PRODUCT_KEY}"
  Delete "$INSTDIR\static\index.html"
  Delete "$INSTDIR\static\app.css"
  Delete "$INSTDIR\static\app.js"
  RMDir "$INSTDIR\static"
  Delete "$INSTDIR\main.py"
  Delete "$INSTDIR\requirements.txt"
  Delete "$INSTDIR\run_windows.bat"
  Delete "$INSTDIR\launch-installed.bat"
  Delete "$INSTDIR\config.example.json"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd

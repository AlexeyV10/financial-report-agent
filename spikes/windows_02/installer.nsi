Unicode true
!include MUI2.nsh
!include LogicLib.nsh
!include x64.nsh
Name "Проектная практика · WIN-02"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Проектная практика WIN02"
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID zlib
SetDatablockOptimize on
!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ProjectPracticeWIN02"
!define APPID "ProjectPracticeWIN02-20261111"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Учебное приложение будет установлено для текущего пользователя.$\r$\n$\r$\nИнтернет и настройка Python для запуска не нужны. При удалении программы учебные данные сохраняются."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\ProjectPractice.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Открыть учебное приложение"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

Function CheckRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\ProjectPracticeWIN02") p.r0'
  ${If} $0 <> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "Сначала закройте учебное приложение WIN-02."
    Abort
  ${EndIf}
FunctionEnd

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ; Fixed per-user target. Never accept an arbitrary command-line /D folder.
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Проектная практика WIN02"
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Для этого примера нужна Windows 11 x64."
    Abort
  ${EndIf}
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
  ${If} $0 < 22000
    MessageBox MB_OK|MB_ICONSTOP "Для этого примера нужна Windows 11."
    Abort
  ${EndIf}
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" "Release"
  ${If} $0 < 528040
    MessageBox MB_OK|MB_ICONSTOP "На компьютере отсутствует требуемый .NET Framework 4.8. Установка остановлена."
    Abort
  ${EndIf}
  Call CheckRunning
  IfFileExists "$INSTDIR\*.*" 0 empty
    MessageBox MB_OK|MB_ICONSTOP "Папка WIN-02 уже существует. Сначала удалите прежнюю установку; ваши учебные данные сохранятся."
    Abort
  empty:
FunctionEnd

Section "Учебное приложение"
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "${PAYLOAD}\*"
  IfErrors failed
  !include "${READONLY_LIST}"
  WriteINIStr "$INSTDIR\install.ini" "Install" "Owner" "${APPID}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Проектная практика WIN02"
  CreateShortcut "$SMPROGRAMS\Проектная практика WIN02\Финансовые документы.lnk" "$INSTDIR\ProjectPractice.exe" "" "$INSTDIR\ProjectPractice.exe"
  CreateShortcut "$SMPROGRAMS\Проектная практика WIN02\Удалить приложение.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${APPKEY}" "DisplayName" "Проектная практика · WIN-02"
  WriteRegStr HKCU "${APPKEY}" "DisplayVersion" "0.0.2-spike"
  WriteRegStr HKCU "${APPKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APPKEY}" "DisplayIcon" "$INSTDIR\ProjectPractice.exe"
  WriteRegStr HKCU "${APPKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
  IfErrors failed
  Goto complete
  failed:
    MessageBox MB_OK|MB_ICONSTOP "Установка не завершена. Учебные данные сохранены. Закройте окно и проверьте свободное место."
    SetErrorLevel 1
    Abort
  complete:
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  StrCpy $1 "$LOCALAPPDATA\Programs\Проектная практика WIN02"
  ${If} $INSTDIR != $1
    MessageBox MB_OK|MB_ICONSTOP "Неизвестная папка установки. Удаление остановлено."
    Abort
  ${EndIf}
  ReadINIStr $0 "$INSTDIR\install.ini" "Install" "Owner"
  ${If} $0 != "${APPID}"
    MessageBox MB_OK|MB_ICONSTOP "Не найдена запись этой установки. Удаление остановлено."
    Abort
  ${EndIf}
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\ProjectPracticeWIN02") p.r0'
  ${If} $0 <> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "Сначала закройте учебное приложение WIN-02."
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  ; Generated exact owned file list; unknown files are preserved. No recursive delete.
  !include "${UNINSTALL_LIST}"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\install.ini"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\Проектная практика WIN02\Финансовые документы.lnk"
  Delete "$SMPROGRAMS\Проектная практика WIN02\Удалить приложение.lnk"
  RMDir "$SMPROGRAMS\Проектная практика WIN02"
  DeleteRegKey HKCU "${APPKEY}"
  DetailPrint "Учебные данные сохранены в отдельной пользовательской папке."
SectionEnd

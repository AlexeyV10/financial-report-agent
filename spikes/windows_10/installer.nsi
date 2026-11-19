Unicode true
!include MUI2.nsh
!include LogicLib.nsh
!include x64.nsh

!define PRODUCT "Финансовый ассистент · Проектная практика"
!define PROGRAM_DIR "Проектная практика D0"
!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ProjectPracticeWIN10"
!define APPID "ProjectPracticeWIN10-D0"
!define MUTEX "Local\ProjectPracticeWIN10"
Name "${PRODUCT}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\${PROGRAM_DIR}"
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID zlib
SetDatablockOptimize on
Var LaunchGuard

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Приложение будет установлено для текущего пользователя.$\r$\n$\r$\nОно работает без сети и установленного Python. При удалении программы проекты сохраняются."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\ProjectPractice.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Открыть финансовый ассистент"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

!macro AcquireGuard
  System::Call 'kernel32::CreateMutexW(p 0, i 1, w "${MUTEX}") p.r0 ?e'
  Pop $1
  ${If} $0 == 0
  ${OrIf} $1 == 183
    ${If} $0 != 0
      System::Call 'kernel32::CloseHandle(p r0)'
    ${EndIf}
    MessageBox MB_OK|MB_ICONSTOP "Закройте приложение или другую установку и повторите операцию." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  StrCpy $LaunchGuard $0
!macroend

!macro ReleaseGuard
  System::Call 'kernel32::ReleaseMutex(p $LaunchGuard)'
  System::Call 'kernel32::CloseHandle(p $LaunchGuard)'
  StrCpy $LaunchGuard 0
!macroend

!macro RejectRedirectedPath PATH
  System::Call 'kernel32::GetFileAttributesW(w "${PATH}") i.r0 ?e'
  Pop $1
  ${If} $0 == -1
  ${AndIf} $1 != 2
  ${AndIf} $1 != 3
    MessageBox MB_OK|MB_ICONSTOP "Папка установки недоступна." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ${If} $0 != -1
    IntOp $0 $0 & 0x400
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "Указана перенаправленная папка установки. Операция остановлена." /SD IDOK
      SetErrorLevel 1
      Abort
    ${EndIf}
  ${EndIf}
!macroend

!macro CleanupInstall
  SetOutPath "$TEMP"
  !include "${UNINSTALL_GUARD_LIST}"
  !include "${UNINSTALL_LIST}"
  Delete "$INSTDIR\Uninstall.exe"
  SetFileAttributes "$INSTDIR\install.ini" NORMAL
  Delete "$INSTDIR\install.ini"
  RMDir "$INSTDIR"
  !insertmacro RejectRedirectedPath "$SMPROGRAMS\${PROGRAM_DIR}"
  Delete "$SMPROGRAMS\${PROGRAM_DIR}\Финансовый ассистент.lnk"
  Delete "$SMPROGRAMS\${PROGRAM_DIR}\Удалить приложение.lnk"
  RMDir "$SMPROGRAMS\${PROGRAM_DIR}"
  DeleteRegKey HKCU "${APPKEY}"
!macroend

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ; Keep the fixed per-user target even when /D is present.
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\${PROGRAM_DIR}"
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Нужна Windows 11 x64." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
  ${If} $0 < 22000
    MessageBox MB_OK|MB_ICONSTOP "Нужна Windows 11." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" "Release"
  ${If} $0 < 528040
    MessageBox MB_OK|MB_ICONSTOP "Нужен .NET Framework 4.8." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  !insertmacro AcquireGuard
  !insertmacro RejectRedirectedPath "$LOCALAPPDATA"
  !insertmacro RejectRedirectedPath "$LOCALAPPDATA\Programs"
  !insertmacro RejectRedirectedPath "$INSTDIR"
  !insertmacro RejectRedirectedPath "$SMPROGRAMS\${PROGRAM_DIR}"
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR") i.r0'
  ${If} $0 != -1
    MessageBox MB_OK|MB_ICONSTOP "Папка установки уже существует. Сначала удалите предыдущую установку. Проекты сохранятся." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ReadRegStr $0 HKCU "${APPKEY}" "DisplayName"
  ${If} $0 != ""
  ${OrIf} ${FileExists} "$SMPROGRAMS\${PROGRAM_DIR}\Финансовый ассистент.lnk"
  ${OrIf} ${FileExists} "$SMPROGRAMS\${PROGRAM_DIR}\Удалить приложение.lnk"
    MessageBox MB_OK|MB_ICONSTOP "Уже найдены записи предыдущей установки. Проекты сохранятся после её удаления." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
FunctionEnd

Section "Финансовый ассистент"
  ClearErrors
  SetOutPath "$INSTDIR"
  IfErrors failed_without_payload
  File /r "${PAYLOAD}\*"
  IfErrors failed
  !include "${READONLY_LIST}"
  IfErrors failed
  WriteINIStr "$INSTDIR\install.ini" "Install" "Owner" "${APPID}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  IfErrors failed
  CreateDirectory "$SMPROGRAMS\${PROGRAM_DIR}"
  CreateShortcut "$SMPROGRAMS\${PROGRAM_DIR}\Финансовый ассистент.lnk" "$INSTDIR\ProjectPractice.exe" "" "$INSTDIR\ProjectPractice.exe"
  CreateShortcut "$SMPROGRAMS\${PROGRAM_DIR}\Удалить приложение.lnk" "$INSTDIR\Uninstall.exe"
  IfErrors failed
  WriteRegStr HKCU "${APPKEY}" "DisplayName" "${PRODUCT}"
  WriteRegStr HKCU "${APPKEY}" "DisplayVersion" "0.1.0-d0"
  WriteRegStr HKCU "${APPKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APPKEY}" "DisplayIcon" "$INSTDIR\ProjectPractice.exe"
  WriteRegStr HKCU "${APPKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
  IfErrors failed
  SetFileAttributes "$INSTDIR\install.ini" READONLY
  IfErrors failed
  !insertmacro ReleaseGuard
  Goto complete
  failed:
    !insertmacro CleanupInstall
  failed_without_payload:
    MessageBox MB_OK|MB_ICONSTOP "Установка не завершилась. Проверьте свободное место и доступ к папке установки." /SD IDOK
    SetErrorLevel 1
    Abort
  complete:
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  StrCpy $1 "$LOCALAPPDATA\Programs\${PROGRAM_DIR}"
  ${If} $INSTDIR != $1
    MessageBox MB_OK|MB_ICONSTOP "Неизвестная папка установки." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  !insertmacro AcquireGuard
  !insertmacro RejectRedirectedPath "$LOCALAPPDATA"
  !insertmacro RejectRedirectedPath "$LOCALAPPDATA\Programs"
  !insertmacro RejectRedirectedPath "$INSTDIR"
  !insertmacro RejectRedirectedPath "$INSTDIR\install.ini"
  ReadINIStr $0 "$INSTDIR\install.ini" "Install" "Owner"
  ${If} $0 != "${APPID}"
    MessageBox MB_OK|MB_ICONSTOP "Не найдена запись этой установки. Удаление остановлено." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  ; Only the generated exact owned file list and application registration.
  !insertmacro CleanupInstall
  DetailPrint "Проекты сохранены в данных текущего пользователя."
  !insertmacro ReleaseGuard
SectionEnd

; Установщик Kostik для Windows 10/11: для текущего пользователя, без прав администратора (#156)
Unicode true
!include MUI2.nsh
!include FileFunc.nsh
Name "Kostik ${DISPLAYVER}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Kostik"
InstallDirRegKey HKCU "Software\DXA QC" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Kostik · команда «Квантовый Скачок»"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Kostik"
VIAddVersionKey "FileDescription" "Установка Kostik ${DISPLAYVER}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${DISPLAYVER}"
VIAddVersionKey "CompanyName" "команда «Квантовый Скачок»"
VIAddVersionKey "LegalCopyright" "© 2026 авторы Kostik"
!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Установка Kostik ${DISPLAYVER}"
!define MUI_WELCOMEPAGE_TEXT "Программа проверяет качество снимков денситометрии DXA: область, вердикт и причина брака по каждому снимку, разметка, 3D-модель и пояснение решения.$\r$\n$\r$\nРаботает на этом компьютере без интернета — снимки никуда не отправляются.$\r$\n$\r$\nНажмите «Далее»."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Kostik.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Открыть Kostik"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\python\python.exe"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Проверить установку (самопроверка)"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION SelfTest
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENSE}"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

Function SelfTest
  ExecWait '"$INSTDIR\selftest.cmd"'
FunctionEnd

Section "Kostik (обязательно)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*"
  WriteUninstaller "$INSTDIR\Удалить Kostik.exe"
  ; прежнее название приложения — DXA QC: убрать старые ярлыки и запускатель при обновлении
  RMDir /r "$SMPROGRAMS\DXA QC"
  Delete "$DESKTOP\DXA QC.lnk"
  Delete "$INSTDIR\DXA QC.exe"
  Delete "$INSTDIR\Удалить DXA QC.exe"
  CreateDirectory "$SMPROGRAMS\Kostik"
  CreateShortcut "$SMPROGRAMS\Kostik\Kostik.lnk" "$INSTDIR\Kostik.exe" "" "$INSTDIR\icon.ico"
  CreateShortcut "$SMPROGRAMS\Kostik\Проверка установки.lnk" "$INSTDIR\selftest.cmd" "" "$INSTDIR\icon.ico"
  CreateShortcut "$SMPROGRAMS\Kostik\Удалить Kostik.lnk" "$INSTDIR\Удалить Kostik.exe"
  WriteRegStr HKCU "Software\DXA QC" "InstallDir" "$INSTDIR"
  !define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\DXAQC"
  WriteRegStr HKCU "${UNKEY}" "DisplayName" "Kostik"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${DISPLAYVER}"
  WriteRegStr HKCU "${UNKEY}" "Publisher" "команда «Квантовый Скачок»"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '"$INSTDIR\Удалить Kostik.exe"'
  WriteRegStr HKCU "${UNKEY}" "QuietUninstallString" '"$INSTDIR\Удалить Kostik.exe" /S'
  WriteRegStr HKCU "${UNKEY}" "URLInfoAbout" "https://ltz2026.ru"
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${UNKEY}" "EstimatedSize" $0
SectionEnd

Section "Ярлык на рабочем столе" SecDesktop
  CreateShortcut "$DESKTOP\Kostik.lnk" "$INSTDIR\Kostik.exe" "" "$INSTDIR\icon.ico"
SectionEnd

Section /o "Открывать файлы .dcm в Kostik" SecAssoc
  WriteRegStr HKCU "Software\Classes\DXAQC.dcm" "" "Снимок DICOM"
  WriteRegStr HKCU "Software\Classes\DXAQC.dcm\DefaultIcon" "" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "Software\Classes\DXAQC.dcm\shell\open\command" "" '"$INSTDIR\Kostik.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.dcm\OpenWithProgids" "DXAQC.dcm" ""
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$DESKTOP\Kostik.lnk"
  RMDir /r "$SMPROGRAMS\Kostik"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DXAQC"
  DeleteRegKey HKCU "Software\DXA QC"
  DeleteRegKey HKCU "Software\Classes\DXAQC.dcm"
  DeleteRegValue HKCU "Software\Classes\.dcm\OpenWithProgids" "DXAQC.dcm"
SectionEnd

LangString DESC_Main ${LANG_RUSSIAN} "Программа, справка и модель бедра (около 300 МБ)."
LangString DESC_Desk ${LANG_RUSSIAN} "Значок Kostik на рабочем столе."
LangString DESC_Assoc ${LANG_RUSSIAN} "Пункт «Открыть с помощью Kostik» для файлов .dcm."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} $(DESC_Main)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_Desk)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAssoc} $(DESC_Assoc)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

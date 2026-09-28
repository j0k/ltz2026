; Запускатель «Kostik.exe»: значок в Пуске и на рабочем столе, передаёт файлы из «Открыть с помощью»
Unicode true
!include FileFunc.nsh
Name "Kostik"
OutFile "${OUTFILE}"
Icon "${ICON}"
RequestExecutionLevel user
SilentInstall silent
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Kostik"
VIAddVersionKey "FileDescription" "Kostik — контроль качества денситометрии"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${DISPLAYVER}"
VIAddVersionKey "LegalCopyright" "© 2026 авторы Kostik"
Section
  ${GetParameters} $R0
  Exec '"$EXEDIR\python\pythonw.exe" -m dxaqc.desktop $R0'
SectionEnd

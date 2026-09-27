; Запускатель «DXA QC.exe»: значок в Пуске и на рабочем столе, передаёт файлы из «Открыть с помощью»
Unicode true
!include FileFunc.nsh
Name "DXA QC"
OutFile "${OUTFILE}"
Icon "${ICON}"
RequestExecutionLevel user
SilentInstall silent
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "DXA QC"
VIAddVersionKey "FileDescription" "DXA QC — контроль качества денситометрии"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "© 2026 авторы DXA QC"
Section
  ${GetParameters} $R0
  Exec '"$EXEDIR\python\pythonw.exe" -m dxaqc.desktop $R0'
SectionEnd

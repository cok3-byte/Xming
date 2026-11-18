; Instalador de Xming (fork no oficial) para NSIS 3. Lo genera winbuild\package.ps1:
;   makensis /DVERSION=1.0.0 /DDIST=<dist> /DOUTFILE=<setup.exe> xming.nsi
;
; Instala en Program Files (x86)\Xming fork, crea accesos en el menú Inicio, asocia
; los .xlaunch a XLaunch y se registra en "Aplicaciones instaladas". No toca el
; Firewall de Windows: la primera vez que Xming escucha, Windows pregunta.

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !error "Falta /DVERSION=x.y.z"
!endif
!ifndef DIST
  !error "Falta /DDIST=<carpeta dist>"
!endif
!ifndef OUTFILE
  !define OUTFILE "Xming-fork-${VERSION}-setup.exe"
!endif

!define PRODUCT "Xming fork"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\XmingFork"
!define REPO_URL "https://github.com/cok3-byte/Xming"

Name "${PRODUCT} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES32\${PRODUCT}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ManifestDPIAware true

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "Instalador de ${PRODUCT} (basado en Xming 6.9.0.31)"
VIAddVersionKey "LegalCopyright" "MIT y licencias de terceros (COPYING.txt)"

!define MUI_ICON "..\..\programs\Xserver\hw\xwin\X.ico"
!define MUI_UNICON "..\..\programs\Xserver\hw\xwin\X.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\XLaunch.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir XLaunch"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${DIST}\COPYING.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

Section "Xming" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "${DIST}\Xming.exe"
  File "${DIST}\XLaunch.exe"
  File "${DIST}\XLaunch.xsd"
  File "${DIST}\xkbcomp.exe"
  File "${DIST}\libfreetype-6.dll"
  File "${DIST}\rgb.txt"
  File "${DIST}\XErrorDB"
  File "${DIST}\XKeysymDB"
  File "${DIST}\COPYING.txt"
  File /r "${DIST}\fonts"
  File /r "${DIST}\locale"
  ; Los mapas compilados por xkbcomp van a %TEMP% (xkb/ddxLoad.c): la carpeta de
  ; instalación no necesita permisos de escritura para el usuario.
  File /r "${DIST}\xkb"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Menú Inicio (todos los usuarios)
  SetShellVarContext all
  CreateDirectory "$SMPROGRAMS\${PRODUCT}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT}\Xming.lnk" "$INSTDIR\Xming.exe" ":0 -multiwindow" "$INSTDIR\Xming.exe" 0
  CreateShortcut "$SMPROGRAMS\${PRODUCT}\XLaunch.lnk" "$INSTDIR\XLaunch.exe" "" "$INSTDIR\XLaunch.exe" 0
  CreateShortcut "$SMPROGRAMS\${PRODUCT}\Licencias.lnk" "$INSTDIR\COPYING.txt"
  CreateShortcut "$SMPROGRAMS\${PRODUCT}\Desinstalar.lnk" "$INSTDIR\uninstall.exe"

  ; .xlaunch: abrir = ejecutar la sesión, editar = abrir el asistente con ella
  WriteRegStr HKLM "Software\Classes\.xlaunch" "" "XmingFork.XLaunch"
  WriteRegStr HKLM "Software\Classes\XmingFork.XLaunch" "" "Configuración de XLaunch"
  WriteRegStr HKLM "Software\Classes\XmingFork.XLaunch\DefaultIcon" "" '"$INSTDIR\XLaunch.exe",0'
  WriteRegStr HKLM "Software\Classes\XmingFork.XLaunch\shell\open\command" "" '"$INSTDIR\XLaunch.exe" -run "%1"'
  WriteRegStr HKLM "Software\Classes\XmingFork.XLaunch\shell\edit\command" "" '"$INSTDIR\XLaunch.exe" -load "%1"'

  ; Aplicaciones instaladas
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${PRODUCT} ${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "Contribuidores del fork de Xming"
  WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "${REPO_URL}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" '"$INSTDIR\Xming.exe",0'
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

; El desinstalador solo borra lo que instaló: si se eligió una carpeta con otros
; ficheros (por ejemplo, C:\), no se pierden.
Section "Uninstall"
  SetShellVarContext all
  Delete "$INSTDIR\Xming.exe"
  Delete "$INSTDIR\XLaunch.exe"
  Delete "$INSTDIR\XLaunch.xsd"
  Delete "$INSTDIR\xkbcomp.exe"
  Delete "$INSTDIR\libfreetype-6.dll"
  Delete "$INSTDIR\rgb.txt"
  Delete "$INSTDIR\XErrorDB"
  Delete "$INSTDIR\XKeysymDB"
  Delete "$INSTDIR\COPYING.txt"
  RMDir /r "$INSTDIR\fonts"
  RMDir /r "$INSTDIR\locale"
  RMDir /r "$INSTDIR\xkb"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  RMDir /r "$SMPROGRAMS\${PRODUCT}"

  ReadRegStr $0 HKLM "Software\Classes\.xlaunch" ""
  StrCmp $0 "XmingFork.XLaunch" 0 +2
    DeleteRegKey HKLM "Software\Classes\.xlaunch"
  DeleteRegKey HKLM "Software\Classes\XmingFork.XLaunch"
  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd

# Changelog

Todos los cambios relevantes de este fork se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). La numeración parte de la
versión original de Xming (6.9.0.31); el historial anterior está en `ChangeLog` y
`programs/Xserver/hw/xwin/ChangeLog`.

## [Unreleased]

### Added
- Build reproducible nativo en Windows con MSYS2 + mingw-w64 (`winbuild/setup.ps1`,
  `winbuild/build.ps1`), sin depender de Cygwin ni de compilación cruzada desde Linux.
  Usa todos los núcleos por defecto y tiene un modo `-Incremental` para iterar rápido.
- `dist/` listo para ejecutar: `Xming.exe`, `xkbcomp.exe`, `libfreetype-6.dll`, datos XKB,
  base de locales de Xlib, `rgb.txt`, `XErrorDB` y `XKeysymDB`.
- Workflow de GitHub Actions que compila en `windows-latest` y publica `dist/` como artefacto.
- Clipboard: `-noclipboard` para desactivarlo, `-noprimary` / `-primary` para decidir si la
  selección PRIMARY (texto seleccionado en un cliente X) también sustituye al portapapeles de
  Windows, `-clipboardtimeout ms` y `-clipboardmaxsize MB`.
### Changed
- El clipboard está activo por defecto; `-clipboard` se acepta por compatibilidad.
  XLaunch pasa `-noclipboard` cuando se desmarca la casilla.
- La copia de trabajo usa siempre finales de línea LF (`.gitattributes`), necesario para que
  imake y make funcionen en Windows.
- El código se adapta a gcc 16 y a las cabeceras de mingw-w64 (choques de nombres entre
  X11 y Win32, `ar` de binutils moderno, winpthreads en lugar de pthreads-win32).

### Fixed
- `winbuild/build.sh` daba por bueno un build en el que no se había podido compilar el
  servidor (con `make -k` quedaba el `Xming.exe` anterior); ahora lo borra antes de compilar.
- Clipboard: cada conversión X→Windows se daba por fallida aunque funcionara, porque
  `XConvertSelection` devuelve 1 y no `Success`; el pegado dependía de que la respuesta
  llegara a tiempo por casualidad.
- Clipboard: se perdía una copia completa del texto en cada pegado X→Windows (fuga de
  memoria) y faltaban comprobaciones de memoria al convertir textos.
- Clipboard: la espera de un pegado podía agotar el timeout aunque la respuesta ya
  estuviera recibida en la cola de Xlib.
- Crash al arrancar con optimización: los callbacks de XACE recibían punteros a datos de un
  bloque que ya había terminado (`Xext/xace.c`). El compilador de 2005 lo toleraba por azar.
- Crash al arrancar con optimización: `SHGetFolderPathA` y `EnumDisplayMonitors` se llamaban
  mediante punteros sin `WINAPI`, lo que desbalanceaba la pila.
- Con `-auth`, el gestor de ventanas multiwindow y el clipboard no podían conectarse al
  propio servidor: ahora usan una cookie interna también en ese caso, no solo con XDMCP.
  Permite usar `-auth` en lugar de `-ac` (servidor abierto a cualquiera).
- Las funciones OpenGL ≥ 1.2 del servidor no enlazaban con mingw-w64 (`gl.h` las declaraba
  `dllimport`).
- El bootstrap de imake no compilaba fuera de compilación cruzada y no podía usar `/tmp` en
  Windows.
- Recursos de Windows: faltaban `version.def` y `X.bmp` en el código publicado; `X.bmp` se
  genera desde `X.ico` con `winbuild/ico2bmp.py`.

## [6.9.0.31] - 2007

### Added
- Copia sin modificar del código fuente de Xming 6.9.0.31 publicada en SourceForge.

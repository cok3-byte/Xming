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
- Clipboard: textos grandes en ambos sentidos con el protocolo INCR de ICCCM. Antes, los
  textos grandes copiados desde aplicaciones GTK/Qt llegaban vacíos a Windows.
- `winbuild/tests/cliptest.py`: pruebas del clipboard contra clientes X reales en WSL.
- Multiwindow: títulos Unicode. Se lee `_NET_WM_NAME` (UTF-8, el que usan GTK y Qt) y las
  ventanas son Unicode, así que acentos, símbolos y CJK ya no se pierden en el título ni en
  la barra de tareas.
- Multiwindow: `_NET_WM_STATE` de EWMH (maximizar, pantalla completa y siempre encima),
  tanto pedido por el cliente como fijado antes de mostrarse. Xming se anuncia como WM EWMH
  (`_NET_SUPPORTING_WM_CHECK`, `_NET_SUPPORTED`).
- Rueda horizontal del ratón (botones X 6 y 7).
### Changed
- Xming es *DPI-aware*: en pantallas al 125 % o 150 % las ventanas ya no se ven borrosas
  por el escalado de Windows, y el DPI por defecto es el del sistema en lugar de 75 (`-dpi`
  sigue mandando). Las aplicaciones X que no escalan solas se verán más pequeñas.
- Los botones laterales del ratón (atrás/adelante) pasan de 6/7 a 8/9, la convención de X;
  6/7 quedan para la rueda horizontal.
- El clipboard está activo por defecto; `-clipboard` se acepta por compatibilidad.
  XLaunch pasa `-noclipboard` cuando se desmarca la casilla.
- El clipboard usa `AddClipboardFormatListener` (Vista o posterior) en lugar de la cadena de
  visores de Windows, que se rompía cuando otra aplicación no reenviaba los mensajes (por
  ejemplo, Escritorio remoto). En sistemas sin esa API se mantiene la cadena.
- Al pegar en Windows desde X se pide primero `UTF8_STRING`, que ofrecen casi todos los
  clientes modernos, en lugar de `COMPOUND_TEXT`.
- La copia de trabajo usa siempre finales de línea LF (`.gitattributes`), necesario para que
  imake y make funcionen en Windows.
- El código se adapta a gcc 16 y a las cabeceras de mingw-w64 (choques de nombres entre
  X11 y Win32, `ar` de binutils moderno, winpthreads en lugar de pthreads-win32).

### Fixed
- Un ratón del que Windows informa con 3 botones podía hacer leer a Xming fuera del mapa de
  botones al pulsar un botón lateral.
- Clipboard: al pegar en Windows un texto copiado en X, Xming vaciaba el portapapeles para
  volver a anunciarlo mientras la aplicación que pegaba aún estaba copiando los datos. Los
  textos grandes (unos 2 MB o más) llegaban vacíos y el primer pegado tras arrancar fallaba
  a veces. Ahora espera a que el portapapeles quede libre.
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

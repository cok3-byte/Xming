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
- `winbuild/tests/desktest.py`: pruebas de integración con el escritorio desde WSL.
- XLaunch se compila y se distribuye en `dist/` junto a Xming, con un `XLaunch.xsd` propio
  (el de Xming 7.x no es redistribuible) que acepta atributos de versiones más nuevas.
- XLaunch usa el OpenSSH integrado en Windows 10/11 sin pedir la ruta de `ssh.exe`.
- XLaunch: con la casilla de compresión, OpenSSH recibe además `ServerAliveInterval=30` para
  que las conexiones lentas no se corten por inactividad.
- `winbuild/tests/sshtest.py`: pruebas del backing store y de cómo lanza XLaunch a Xming y ssh.
- README: cómo usar aplicaciones remotas por SSH, cuándo comprimir y cómo medir.
- Fuentes bitmap en `dist/fonts/` (`misc`, `75dpi` y `100dpi`, unos 15 MB comprimidas), con
  `fonts.dir` y `fonts.alias`: `fixed` y las fuentes Unicode que usa xterm ya existen y las
  aplicaciones dejan de avisar de fuentes que faltan.
- Fuentes del usuario: `%APPDATA%\Xming\fonts` y cada subcarpeta suya con `fonts.dir` se
  añaden al font path al arrancar, sin permisos de administrador.
### Changed
- Backing store activo por defecto (equivale a `+bs -wm`): al destapar una ventana X el
  servidor restaura su contenido en lugar de pedir al cliente que la redibuje, lo que ahorra
  tráfico a través de SSH. `-bs` lo desactiva.
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
- `-auth` rechazaba a veces clientes con la cookie correcta: el servidor leía el fichero de
  autorización en modo texto, así que una cookie con un byte `0x1A` o con CR LF llegaba
  corrompida (aproximadamente 1 de cada 15 cookies aleatorias).
- El build con MSYS2 convertía las rutas Unix de los `-D` (por ejemplo `/usr/X11R6` pasaba a
  `C:/msys64/usr/X11R6`), así que Xming no reubicaba a su carpeta ni las fuentes ni
  `rgb.txt`: no encontraba ninguna fuente en disco ni los nombres de color.
- Un ratón del que Windows informa con 3 botones podía hacer leer a Xming fuera del mapa de
  botones al pulsar un botón lateral.

### Security
- XLaunch lanzaba `Xming`, `ssh` y `plink` por nombre, y Windows los busca también en el
  directorio actual: un ejecutable con ese nombre dejado ahí se ejecutaba en su lugar. Ahora
  usa rutas absolutas entre comillas.
- XLaunch: los mensajes de error al cargar un `.xlaunch` podían desbordar un búfer con un
  nombre de fichero largo.
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

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
- `winbuild/tests/fonttest.py`: pruebas de fuentes contra clientes X reales en WSL.
- GLX 1.3: `glXCreateWindow`/`glXDestroyWindow`, `glXQueryDrawable` y `glXQueryContext`
  (lo usa `glXImportContextEXT`). Faltan los pbuffers.
- El log de Xming dice qué driver OpenGL de Windows dibuja GLX, y avisa si es el
  renderizador por software de Microsoft ("GDI Generic").
- `winbuild/tests/gltest.py`: pruebas de OpenGL indirecto con `glxinfo`, `glxgears` y una
  sonda de GLX 1.3 desde WSL.
- README: cómo usar OpenGL y sus límites (OpenGL 1.x indirecto, sin OpenGL 3+).
- Licencia MIT para los cambios del fork (`LICENSE`) y `THIRD-PARTY-NOTICES.txt` con las
  licencias de cada componente. El build las reúne en `dist/COPYING.txt`, junto con la
  licencia de FreeType, que exige acompañar a los binarios.
- `-hostintitle`: en multiwindow, el título de las ventanas de clientes de otro equipo
  lleva " @ equipo", para distinguir el mismo programa abierto en varios servidores.
- `+byteswappedclients` para aceptar clientes con el otro orden de bytes (ver *Security*).
- El log indica la versión real de Windows (antes decía "Vista" en Windows 11).
- XLaunch: con el campo Display vacío usa el primer display libre.
- XLaunch: un nombre relativo de `.xlaunch` en `-run`/`-load`/`-validate` se busca
  también en `%APPDATA%\Xming`, el Escritorio, el perfil y la carpeta de XLaunch, con o sin
  la extensión. Al guardar se añade `.xlaunch` si falta.
- XLaunch: F1/Help muestra un resumen de cada página cuando no está `XLaunch.chm` (la ayuda
  de Xming no es redistribuible y no se incluye); antes no pasaba nada.
- `winbuild/tests/xltest.py`: pruebas de estas opciones y de XLaunch desde Windows y WSL.
### Changed
- XLaunch deja Xming abierto cuando termina el programa que lanzó (por ejemplo, al salir
  de la sesión ssh); antes lo cerraba en ese momento. Se cierra desde la bandeja.
- XLaunch ya no enlaza libX11: comprueba que Xming ha arrancado conectando a su puerto
  TCP, y deja de mantener abierta una conexión X que nunca cerraba.
- El fork se identifica como tal: el *vendor string* del servidor, el contacto del log y
  el diálogo About dicen que es un fork no oficial, y el botón "Fork" abre su repositorio.
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
- El timbre sonaba aunque se hubiera silenciado (`xset b off`, `-f 0`).
- XLaunch: si Xming no arrancaba, lanzaba igualmente el programa; y si el programa no se
  podía lanzar, seguía esperando con un identificador de proceso inválido.
- XLaunch: con un display ya en uso lanzaba el programa contra el otro servidor; ahora
  avisa y no arranca nada.
- XLaunch: guardar la configuración y elegir la ruta de plink/ssh usaban punteros a datos
  ya liberados, y el diálogo de ruta creía tener un búfer del doble de su tamaño.
- XLaunch: los argumentos con caracteres fuera de la página de códigos ANSI (rutas de
  `.xlaunch` con otros alfabetos) se perdían.
- OpenGL no funcionaba con clientes actuales: Mesa actual (probado con 25.2) exige un servidor
  GLX 1.3 y Xming anunciaba 1.2, así que `glxinfo`, `glxgears` y cualquier aplicación GL
  fallaban con "couldn't find RGB GLX visual". Ahora anuncia GLX 1.3 y los FBConfigs
  incluyen `GLX_DRAWABLE_TYPE` y `GLX_RENDER_TYPE`. El dibujo lo hace la GPU de Windows.
- `-auth` rechazaba a veces clientes con la cookie correcta: el servidor leía el fichero de
  autorización en modo texto, así que una cookie con un byte `0x1A` o con CR LF llegaba
  corrompida (aproximadamente 1 de cada 15 cookies aleatorias).
- El build con MSYS2 convertía las rutas Unix de los `-D` (por ejemplo `/usr/X11R6` pasaba a
  `C:/msys64/usr/X11R6`), así que Xming no reubicaba a su carpeta ni las fuentes ni
  `rgb.txt`: no encontraba ninguna fuente en disco ni los nombres de color.
- Un ratón del que Windows informa con 3 botones podía hacer leer a Xming fuera del mapa de
  botones al pulsar un botón lateral.

### Security
- Los clientes con el otro orden de bytes se rechazan por defecto, como en xorg-server
  actual: el código que traduce sus peticiones (`SProc*`) es el de más fallos de seguridad
  conocidos y casi nadie lo necesita. `+byteswappedclients` los vuelve a aceptar.
- "View log" y "View Licence" lanzaban `notepad` por nombre (se buscaba también en el
  directorio actual) y copiaban la ruta en un búfer fijo de 256 bytes. Ahora abren el
  fichero con su programa asociado o el Bloc de notas de la carpeta del sistema, y la
  licencia se busca junto al ejecutable y no en el directorio actual.
- XLaunch: el número de display de un `.xlaunch` se añadía sin comprobar a la línea de
  comandos de Xming (`Display="0 -ac"` desactivaba el control de acceso); ahora solo se
  aceptan dígitos.
- XLaunch pide confirmación al marcar "No Access Control" (`-ac`), que abre el servidor a
  cualquier equipo de la red.
- XLaunch: la contraseña de plink iba sin comillas, así que una con espacios partía la
  línea de comandos y el resto se interpretaba como opciones de plink.
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

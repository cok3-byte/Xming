# Estado del build nativo en Windows (actualizado 2026-11-17)

Documento de traspaso de la **Fase 1** del plan
(`C:\Users\Jorge\.claude\plans\revisa-el-proyecto-y-jiggly-summit.md`):
compilar Xming 6.9.0.31 de forma nativa en Windows con MSYS2 + mingw-w64.

## Resumen

**Xming.exe compila, enlaza y funciona** (gcc 16.2, `-O2`, 32 bits), verificado con clientes
reales desde WSL (Ubuntu 24.04):

- `Xming.exe :5 -multiwindow -clipboard -auth <Xauthority>` (cookie MIT-MAGIC-COOKIE-1, sin `-ac`).
- `xdpyinfo` desde WSL: vendor Colin Harrison, release 60900031, 23 extensiones, 1920x1080.
- `xclock` y `xterm` aparecen como ventanas nativas de Windows (clase `Xming X`); el título
  del xterm se actualiza en vivo.
- Portapapeles Windows→X y X→Windows con Unicode (ñ, €, CJK) en `CLIPBOARD`; Windows→X
  también llega a `PRIMARY`. X→Windows con 400 KB funciona (BIG-REQUESTS evita INCR).

Cómo reproducir la prueba desde WSL (NAT; el host Windows es la puerta de enlace por defecto
de WSL, aquí 172.30.80.1):

1. Generar una cookie aleatoria de 16 bytes y escribir un fichero Xauthority para el servidor
   (entrada FamilyWild, display `5`, `MIT-MAGIC-COOKIE-1`).
2. En WSL: `xauth add <ip-host>:5 MIT-MAGIC-COOKIE-1 <cookie-hex>`.
3. `dist\Xming.exe :5 -multiwindow -clipboard -auth <fichero>` y desde WSL
   `DISPLAY=<ip-host>:5 xclock`. El Firewall de Windows debe permitir Xming.exe en la red
   de WSL (ya lo permitía en esta máquina).
4. Los procesos lanzados con `&` dentro de `wsl -e sh -c` mueren al cerrar esa sesión:
   mantenerla abierta (por ejemplo con `sleep`).

- Worktree: `D:\proyects\Xming-build`, rama `chore/build-reproducible` (desde `master`).
- Todo está commiteado en esa rama, un commit por causa (`git log --oneline master..`),
  sin push ni PR.
- Toolchain: MSYS2 en `C:\msys64`, entorno MINGW32, gcc 16.2.0 i686, binutils 2.47.
  MSYS2 ya no publica `gdb` para i686.
- Plan aparte de mejoras de XmingNotes y XLaunch: `D:\proyects\Xming\docs\plan-xmingnotes-xlaunch.md`
  (en el checkout de `master`, sin commitear).

## Uso

```powershell
.\winbuild\build.ps1                # build completo, 16 hilos
.\winbuild\build.ps1 -Incremental   # ~1 min; recompila solo lo cambiado
dist\Xming.exe :0 -multiwindow -clipboard
```

Logs en `winbuild\out\world.log` / `incremental.log`; log del servidor en
`%TEMP%\Xming.<display>.log`.

Ojo con el modo incremental: imake no rastrea dependencias de cabeceras. Si cambias una
cabecera, borra los `.o` afectados (por ejemplo `programs/Xserver/GL/glx/stdcall/*.o`).

## `dist/`

`Xming.exe`, `xkbcomp.exe`, `libfreetype-6.dll` (FreeType de `extras/`, la única DLL no del
sistema), `xkb/` (datos XKB + `compiled/`), `locale/` (base de locales de Xlib, generada con
cpp porque `BuildServersOnly` no construye `nls/`), `rgb.txt`, `XErrorDB`, `XKeysymDB`.
Unos 6 MB más los datos.

## Bugs reales encontrados (no solo de toolchain)

1. **`Xext/xace.c`**: cada `case` de `XaceHook` guardaba `calldata = &rec` de una variable de
   bloque y llamaba a los callbacks después del `switch`. gcc moderno reutiliza esa memoria →
   el callback de Security leía basura. Ahora los callbacks se llaman dentro del bloque.
2. **`hw/xwin/InitOutput.c`, `winprocarg.c`**: punteros a `SHGetFolderPathA` y
   `EnumDisplayMonitors` sin `WINAPI`. Con `-O2` (sin puntero de marco) la pila quedaba
   desbalanceada y `ret` saltaba a la pila (DEP). gcc < 4.6 conservaba el puntero de marco por
   defecto y lo ocultaba.

3. **`-auth` dejaba sin WM ni clipboard** (`InitOutput.c`, `winprocarg.c`, `winglobals.c`,
   `winmultiwindowwm.c`): la cookie interna solo se generaba con XDMCP, así que con `-auth`
   los hilos internos no podían conectar ("Could not open display" en bucle). Ahora se genera
   también con `-auth`, y los dos hilos del WM la usan con `XSetAuthorization` (antes solo lo
   hacía el del clipboard). Es la mejora S2 de `plan-xmingnotes-xlaunch.md`.

Técnica usada para depurar sin gdb: mini depurador Win32 en Python (ctypes, API de depuración
+ `Wow64GetThreadContext`) y compilar `hw/xwin`, `os`, `dix` con
`CDEBUGFLAGS="-O0 -g -fno-omit-frame-pointer"` para seguir la cadena EBP con `addr2line`.

## Correcciones hechas (un commit por cada fila)

| Causa | Ficheros |
|---|---|
| Bootstrap de imake (`inline_syntax`, `/tmp` → `%TEMP%`) | `config/imake/imake.c` |
| gcc moderno y binutils: `-std=gnu89 -fpermissive -fcommon`, `ar cq`, winpthreads estático | `config/cf/host.def`, `programs/Xserver/Imakefile` (`XWinPThreadLib`) |
| Cabeceras mingw-w64 / X11 (`BOOL`/`wBOOL`, `ControlMask`, `Private`, `Status`) | `include/Xwindows.h`, `include/Xwinsock.h`, `hw/xwin/ddraw.h`, `InitOutput.c`, `winmultiwindowwm.c`, `programs/xkbcomp/listing.c` |
| DirectDraw (`DUMMYUNIONNAMEn`, `GUID_SECT`) | `hw/xwin/ddraw.h`, `winshaddd.c`, `winshadddnl.c` |
| Cast como lvalue | `miext/rootless/rootlessCommon.h`, `rootlessWindow.c`, `rootlessScreen.c`, `accel/rlAccel.c` |
| `stdint.h` | `fb/fbcompose.c`, `hw/xwin/winmultiwindowicons.c` |
| `stricmp` | `extras/rman/rman.c` |
| Recursos (`version.def`, `X.bmp`, icono xkbcomp) | `version.def`, `XWin.rc`, `xlaunch/resources/version.rc`, `programs/xkbcomp/{Imakefile,XKBConf.rc}`, `X.bmp`, `winbuild/ico2bmp.py` |
| GLAPI `dllimport` | `extras/Mesa/include/GL/gl.h` |
| **Bug XACE** | `programs/Xserver/Xext/xace.c` |
| **Bug `WINAPI`** | `hw/xwin/InitOutput.c`, `hw/xwin/winprocarg.c` |
| **Cookie interna con `-auth`** | `hw/xwin/InitOutput.c`, `winprocarg.c`, `winglobals.c`, `winmultiwindowwm.c` |
| Scripts, empaquetado, CI, docs | `winbuild/*`, `.github/workflows/build.yml`, `README`, `CHANGELOG.md`, `.gitignore`, `.gitattributes`, `docs/ESTADO-BUILD.md` |

## Pendiente

1. ~~Commits por causa~~: hechos. Falta decidir push / PR / merge a `master`.
2. Probar la CI (`.github/workflows/build.yml`, nunca ejecutada).
3. ~~Prueba con clientes reales desde WSL~~: hecha (ver Resumen). En la prueba, `xterm` avisó
   de que no encuentra la fuente `-misc-fixed-…-iso10646-1` (solo hay `built-ins`).
   Pendiente para la Fase 5 (fuentes).
4. Ruido no bloqueante en el log de build: `config/util/lndir.c` (`sys/dir.h`) y
   `lib/windows/WindowsWM.man` (comentario sin cerrar en cpp).
5. Avisos del servidor: el layout de teclado `0000080A` (Latinoamericano) no está en
   `winlayouts.h` (cae al por defecto); no hay fuentes en disco, solo las `built-ins`.
   Esto entra en la Fase 5 (fuentes) y en el backlog de teclado.
6. XLaunch todavía no se compila (ver `plan-xmingnotes-xlaunch.md`, sección 5).
7. Validar con el usuario antes de pasar a la Fase 2 (clipboard).

#!/bin/sh
# Ejecutado por winbuild/build.ps1 dentro del shell MINGW32 de MSYS2.
# Uso: build.sh [jobs] [world|incremental]
#   jobs         trabajos paralelos de make (por defecto, todos los núcleos lógicos)
#   world        build completo desde cero (distclean + bootstrap de imake)
#   incremental  recompila solo lo cambiado; requiere un "world" previo
set -eu

JOBS="${1:-$(nproc 2>/dev/null || echo 1)}"
MODE="${2:-world}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"

cd "$ROOT"

if [ "${MSYSTEM:-}" != "MINGW32" ]; then
    echo "Este script debe ejecutarse en el entorno MINGW32 de MSYS2 (MSYSTEM=MINGW32)." >&2
    exit 1
fi

echo "gcc: $(command -v gcc) ($(gcc -dumpmachine), $(gcc -dumpversion))"
echo "modo: $MODE, trabajos paralelos: $JOBS"

BOOT_CFLAGS="-std=gnu89 -fpermissive -fcommon"

# -k sigue tras errores para ver todos de una vez; el resultado se comprueba al final.
# -O agrupa la salida de cada objeto para que el log siga siendo legible en paralelo.
PAR="-k -j$JOBS -Otarget"

# Con -k, un fallo de compilación no detiene make y quedaría el Xming.exe anterior:
# borrarlo garantiza que dist/ solo reciba un binario enlazado en este build.
XMING="programs/Xserver/Xming.exe"
rm -f "$XMING"

case "$MODE" in
    world)
        # Los pasos previos de World (bootstrap, Makefiles, depend) son secuenciales;
        # WORLDOPTS solo afecta a la compilación, que es la parte larga.
        make World CC="gcc $BOOT_CFLAGS" BOOTSTRAPCFLAGS="$BOOT_CFLAGS" WORLDOPTS="$PAR"
        ;;
    incremental)
        if [ ! -f xmakefile ]; then
            echo "No hay xmakefile: ejecuta antes un build completo (modo world)." >&2
            exit 1
        fi
        # "includes" vuelve a copiar las cabeceras editadas a exports/include
        # (MSYS2 copia en lugar de crear enlaces simbólicos).
        # "Makefiles" regenera los Makefile si cambió algún Imakefile o host.def.
        make -f xmakefile Makefiles
        make -f xmakefile includes
        make -f xmakefile $PAR all
        ;;
    *)
        echo "Modo desconocido: $MODE (usa world o incremental)." >&2
        exit 1
        ;;
esac

if [ ! -f "$XMING" ]; then
    echo "No se generó $XMING: revisa el log de build." >&2
    exit 1
fi

# XLaunch (asistente de arranque) no está en el árbol imake: Makefile propio que
# enlaza contra la libX11 de exports/lib.
XLAUNCH_DIR="programs/Xserver/hw/xwin/xlaunch"
rm -f "$XLAUNCH_DIR/XLaunch.exe"
make -C "$XLAUNCH_DIR" -j"$JOBS"

rm -rf "$DIST"
mkdir -p "$DIST"
cp "$XMING" "$DIST/"
for f in programs/Xserver/hw/xwin/xlaunch/XLaunch.exe \
         programs/Xserver/hw/xwin/xlaunch/XLaunch.xsd \
         programs/rgb/rgb.txt \
         programs/xkbcomp/xkbcomp.exe \
         exports/bin/libfreetype-6.dll \
         lib/X11/XErrorDB \
         lib/X11/XKeysymDB; do
    if [ -f "$f" ]; then cp "$f" "$DIST/"; fi
done

# Datos XKB: Xming busca <directorio del exe>\xkb (InitOutput.c, XkbBaseDirectory)
# y escribe ahí los mapas compilados por xkbcomp.
mkdir -p "$DIST/xkb/compiled"
for d in compat geometry keycodes keymap rules semantics symbols types; do
    cp -r "programs/xkbcomp/$d" "$DIST/xkb/"
done
# Quitar restos de imake (Makefile, Imakefile...) de los datos copiados
find "$DIST/xkb" \( -name 'Makefile*' -o -name 'Imakefile' -o -name '*.dep' \) -delete

# Base de datos de locales de Xlib: Xming fija XLOCALEDIR=<directorio del exe>\locale.
# Sin ella el WM multiwindow y el clipboard terminan con "Locale not supported by X".
# BuildServersOnly no genera nls/, así que se preprocesa aquí con la misma regla que
# CppFileTarget de imake (cpp -traditional + XCOMM -> #). WCHAR32 = HasWChar32 (YES).
nls_cpp() {
    # Las líneas "##" de los Compose son comentarios para Xlib pero cpp las rechaza;
    # se descartan igual que con la regla de imake, así que se silencia el aviso.
    cpp -undef -traditional -P -DWCHAR32=1 -DX_LOCALE < "$1" 2>/dev/null | sed \
        -e '/^[ 	]*XCOMM$/s/XCOMM/#/' \
        -e '/^[ 	]*XCOMM[^a-zA-Z0-9_]/s/XCOMM/#/' \
        -e '/^[ 	]*XHASH/s/XHASH/#/' > "$2"
}
mkdir -p "$DIST/locale"
for f in locale.alias locale.dir compose.dir; do
    nls_cpp "nls/$f" "$DIST/locale/$f"
done
for f in nls/XLC_LOCALE/* nls/Compose/*; do
    name="$(basename "$f")"
    case "$name" in Imakefile|Makefile*|*.dep) continue ;; esac
    kind="$(basename "$(dirname "$f")")"   # XLC_LOCALE o Compose
    mkdir -p "$DIST/locale/$name"
    nls_cpp "$f" "$DIST/locale/$name/$kind"
done

echo "Binarios copiados a $DIST:"
ls -l "$DIST"

"""Pruebas de fuentes (Fase 5) contra clientes X reales en WSL.

Uso (con Xming compilado en dist/):
    python -I winbuild/tests/fonttest.py dist [display]

Requisitos: distro WSL "Ubuntu-24.04" con x11-apps, x11-utils, x11-xserver-utils,
xterm y xauth; el Firewall de Windows debe permitir dist/Xming.exe. Crea y borra
%APPDATA%\\Xming\\fonts\\xming-prueba (no toca nada si esa carpeta ya existe).
"""
import os
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
DIST = os.path.abspath(sys.argv[1])
DISP = sys.argv[2] if len(sys.argv) > 2 else "5"
DISTRO = "Ubuntu-24.04"
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")


def wsl(cmd, timeout=90):
    r = subprocess.run(["wsl", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", cmd],
                       capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


host = wsl("ip route show default | cut -d' ' -f3").strip()
TMP = tempfile.mkdtemp(prefix="fonttest-")
AUTH = os.path.join(TMP, "Xauthority")
cookie = secrets.token_bytes(16)


def field(b):
    return struct.pack(">H", len(b)) + b


with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP};"

# Carpeta de fuentes del usuario: una fuente de misc con un nombre XLFD único
USER_DIR = os.path.join(os.environ["APPDATA"], "Xming", "fonts", "xming-prueba")
created_user_dir = False
if not os.path.exists(USER_DIR):
    os.makedirs(USER_DIR)
    created_user_dir = True
    shutil.copy(os.path.join(DIST, "fonts", "misc", "7x13.bdf.gz"), os.path.join(USER_DIR, "prueba.bdf.gz"))
    with open(os.path.join(USER_DIR, "fonts.dir"), "w", encoding="ascii", newline="\n") as f:
        f.write("1\nprueba.bdf.gz -xmingprueba-fixed-medium-r-normal--13-120-75-75-c-70-iso8859-1\n")

errlog = os.path.join(TMP, "xming-stderr.txt")
with open(errlog, "wb") as err:
    srv = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow", "-auth", AUTH],
                           cwd=DIST, stdout=err, stderr=err)
    time.sleep(5)
    try:
        fp = wsl(f"{ENV} xset q | sed -n '/Font Path:/{{n;p}}'").strip()
        check("el font path apunta a dist\\fonts (no a /usr/X11R6)",
              (DIST.lower() + "/fonts/misc") in fp.lower() and "/usr/X11R6" not in fp, fp[:120])
        n_fixed = int(wsl(f"{ENV} xlsfonts -fn '-misc-fixed-*' | wc -l").strip() or 0)
        check("fuentes misc-fixed disponibles", n_fixed > 50, f"{n_fixed} fuentes")
        alias = wsl(f"{ENV} xlsfonts -ll -fn fixed | grep -m1 -E '^[[:space:]]+FONT[[:space:]]'").strip()
        check("el alias 'fixed' resuelve", "misc-fixed" in alias.lower(), alias)
        uni = wsl(f"{ENV} xlsfonts -fn '-misc-fixed-medium-r-semicondensed--13-120-75-75-c-60-iso10646-1'").strip()
        check("fuente Unicode de xterm disponible", "iso10646" in uni.lower(), uni)
        out = wsl(f"{ENV} timeout 8 xterm -e true 2>&1; echo rc=$?")
        check("xterm arranca sin avisos de fuentes",
              out.strip().endswith("rc=0") and "cannot load font" not in out
              and "Missing charsets" not in out and "Invalid" not in out, out.strip()[:150])
        n75 = int(wsl(f"{ENV} xlsfonts -fn '-adobe-helvetica-*-*-*-*-*-*-75-75-*' | wc -l").strip() or 0)
        check("fuentes de 75 dpi (helvetica) disponibles", n75 > 10, f"{n75} fuentes")
        user = wsl(f"{ENV} xlsfonts -fn '-xmingprueba-*'").strip()
        check("fuente de la carpeta del usuario visible", "xmingprueba" in user, user)
    finally:
        srv.kill()
        srv.wait()
log = open(errlog, encoding="latin-1").read()
check("rgb.txt encontrado (sin 'Couldn't open RGB_DB')", "Couldn't open RGB_DB" not in log)
check("Xming informa de la carpeta de fuentes del usuario", "Added user font directory" in log)
if not all(ok for _, ok in results):
    print("--- final del log de Xming:\n" + "\n".join(log.splitlines()[-15:]))

wsl(f"xauth remove {host}:{DISP}; true")
if created_user_dir:
    shutil.rmtree(USER_DIR)
    for d in (os.path.dirname(USER_DIR), os.path.dirname(os.path.dirname(USER_DIR))):
        try:
            os.rmdir(d)  # solo si quedó vacía
        except OSError:
            pass
shutil.rmtree(TMP)
print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

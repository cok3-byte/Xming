"""Pruebas de OpenGL / GLX (Fase 3) contra clientes X reales en WSL.

Uso (con Xming compilado en dist/):
    python -I winbuild/tests/gltest.py dist [display]

Requisitos: distro WSL "Ubuntu-24.04" con mesa-utils (glxinfo, glxgears), x11-utils,
python3 y xauth; el Firewall de Windows debe permitir dist/Xming.exe. Los clientes usan
GLX indirecto (LIBGL_ALWAYS_INDIRECT=1): el renderizado lo hace el driver OpenGL de
Windows a través de WGL.
"""
import os
import re
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
HERE = os.path.dirname(os.path.abspath(__file__))
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")


def wsl(cmd, timeout=90):
    r = subprocess.run(["wsl", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", cmd],
                       capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def field(b):
    return struct.pack(">H", len(b)) + b


host = wsl("ip route show default | cut -d' ' -f3").strip()
probe = wsl(f"wslpath -a '{os.path.join(HERE, 'glx13probe.py')}'").strip()
TMP = tempfile.mkdtemp(prefix="gltest-")
AUTH = os.path.join(TMP, "Xauthority")
cookie = secrets.token_bytes(16)
with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP} LIBGL_ALWAYS_INDIRECT=1;"

errlog = os.path.join(TMP, "xming-stderr.txt")
with open(errlog, "wb") as err:
    srv = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow", "-auth", AUTH],
                           cwd=DIST, stdout=err, stderr=err)
    time.sleep(5)
    try:
        info = wsl(f"{ENV} timeout 20 glxinfo 2>&1")
        ver = re.search(r"server glx version string: (\S+)", info)
        check("el servidor anuncia GLX 1.3", ver is not None and ver.group(1) == "1.3",
              ver.group(1) if ver else info.strip()[:120])
        rend = re.search(r"OpenGL renderer string: (.+)", info)
        check("glxinfo obtiene un renderer OpenGL", rend is not None, rend.group(1) if rend else "")
        check("los clientes ven visuales RGB con doble buffer",
              "couldn't find RGB GLX visual" not in info and rend is not None)

        gears = wsl(f"{ENV} timeout 7 glxgears 2>&1")
        fps = re.findall(r"= ([0-9.]+) FPS", gears)
        check("glxgears dibuja", bool(fps) and float(fps[-1]) > 0,
              f"{fps[-1]} FPS" if fps else gears.strip()[:120])

        out = wsl(f"{ENV} timeout 40 python3 -I '{probe}' 2>&1")
        kv = dict(re.findall(r"(\w+)=(\S+)", out))
        check("glXChooseFBConfig encuentra configs de ventana", int(kv.get("fbconfigs_window_rgba_db", 0)) > 0,
              kv.get("fbconfigs_window_rgba_db", ""))
        check("glXCreateWindow + glXMakeContextCurrent sin errores",
              kv.get("create_errors") == "none" and kv.get("make_current") == "1"
              and kv.get("errors") == "none", out.strip()[:160] if "make_current" not in kv else "")
        check("el contexto dibuja (glClear rojo leído con glReadPixels)",
              kv.get("pixel") == "255,0,0", kv.get("pixel", ""))
        check("glXQueryDrawable devuelve el tamaño", re.fullmatch(r"[1-9]\d*x48", kv.get("drawable_size", "")) is not None,
              kv.get("drawable_size", ""))
        check("glXImportContextEXT (glXQueryContext) desde otra conexión",
              kv.get("import_context") == "ok", kv.get("fbconfig", ""))
        check("glXDestroyWindow sin errores", kv.get("destroy_window_errors") == "none")
        check("destruir la ventana X libera su GLXWindow", kv.get("glxwindow_freed_with_window") == "yes")
        alive = wsl(f"{ENV} xdpyinfo >/dev/null 2>&1 && echo vivo").strip()
        check("el servidor sigue vivo tras las pruebas", alive == "vivo" and srv.poll() is None)
    finally:
        srv.kill()
        srv.wait()
log = open(errlog, encoding="latin-1").read()
wgl = re.search(r"GLX: OpenGL via WGL: (.*)", log)
check("Xming registra el driver OpenGL que usa", wgl is not None, wgl.group(1).strip() if wgl else "")
if not all(ok for _, ok in results):
    print("--- final del log de Xming:\n" + "\n".join(log.splitlines()[-15:]))

wsl(f"xauth remove {host}:{DISP}; true")
shutil.rmtree(TMP)
print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

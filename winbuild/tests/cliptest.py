"""Pruebas del clipboard de Xming contra clientes X reales en WSL.

Uso (desde Windows, con Xming compilado en dist/):
    python -I winbuild/tests/cliptest.py dist [display]

Requisitos:
  - Distro de WSL "Ubuntu-24.04" con xclip y xauth (apt install xclip xauth).
  - El Firewall de Windows debe permitir la entrada a dist/Xming.exe desde la red de WSL.

Cubre: Unicode en ambos sentidos, PRIMARY, textos grandes (INCR, 5 MB X→Windows y
20 MB Windows→X), -noprimary, -noclipboard y el listener de Windows. Genera una cookie
MIT-MAGIC-COOKIE-1 aleatoria por ejecución (sin -ac) y restaura el portapapeles al terminar.
"""
import ctypes
import os
import secrets
import struct
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
DIST = sys.argv[1]
DISP = sys.argv[2] if len(sys.argv) > 2 else "5"
DISTRO = "Ubuntu-24.04"
TMP = tempfile.mkdtemp(prefix="cliptest-")
AUTH = os.path.join(TMP, "Xauthority")
results = []


def wsl(cmd, timeout=60, background=False):
    args = ["wsl", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", cmd]
    if background:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


# --- portapapeles de Windows vía Win32 (sin depender de PowerShell) ---
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32.GetClipboardData.restype = ctypes.c_void_p
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
k32.GlobalAlloc.restype = ctypes.c_void_p
u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
CF_UNICODETEXT = 13


def open_clip():
    for _ in range(50):
        if u32.OpenClipboard(None):
            return
        time.sleep(0.1)
    raise RuntimeError("no se pudo abrir el portapapeles")


def get_clip():
    open_clip()
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def set_clip(text):
    open_clip()
    try:
        u32.EmptyClipboard()
        if text is None:
            return
        data = (text + "\0").encode("utf-16-le")
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        u32.CloseClipboard()


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")


# --- servidor y cookie ---
host = wsl("ip route show default | cut -d' ' -f3").strip()
cookie = secrets.token_bytes(16)


def field(b):
    return struct.pack(">H", len(b)) + b


with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP};"
LOG = os.path.join(os.environ["TEMP"], f"Xming.{DISP}.log")


def start(extra):
    p = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow",
                          "-auth", AUTH, *extra], cwd=DIST)
    time.sleep(5)
    return p


def stop(p):
    p.kill()
    p.wait()
    time.sleep(1)


u32.GetClipboardSequenceNumber.restype = ctypes.c_uint


def x_owner_hold(cmd_producing_data, selection="clipboard", hold=60, expect_windows_change=True):
    """Un cliente X (xclip) se queda como propietario de la selección.

    Espera a que Xming tome el portapapeles de Windows (cambia el número de
    secuencia) en lugar de dormir un tiempo fijo: arrancar WSL y pasar varios MB
    por la tubería tarda un tiempo variable.
    """
    seq = u32.GetClipboardSequenceNumber()
    p = wsl(f"{ENV} {cmd_producing_data} | xclip -i -selection {selection}; sleep {hold}",
            background=True)
    deadline = time.time() + 30
    while expect_windows_change and time.time() < deadline:
        if u32.GetClipboardSequenceNumber() != seq:
            break
        time.sleep(0.2)
    else:
        time.sleep(4 if not expect_windows_change else 0)
    time.sleep(0.5)
    return p


original = get_clip()
try:
    # 1) Por defecto (sin -clipboard): Unicode en ambos sentidos
    srv = start([])
    try:
        txt = "Windows→X: ñandú, €, 日本語"
        set_clip(txt)
        time.sleep(1)
        out = wsl(f"{ENV} timeout 10 xclip -o -selection clipboard")
        check("clipboard por defecto, Windows→X Unicode", out == txt, repr(out[:40]))
        out_p = wsl(f"{ENV} timeout 10 xclip -o -selection primary")
        check("PRIMARY recibe el texto de Windows (por defecto)", out_p == txt)

        w = x_owner_hold(r"printf 'X\342\206\222Windows: a\303\261ejo, \342\202\254, \346\274\242\345\255\227'")

        got = get_clip()
        check("X→Windows Unicode (UTF8_STRING)", got == "X→Windows: añejo, €, 漢字", repr(got))
        w.kill()

        # 2) Textos grandes: 5 MB X→Windows (xclip usa INCR por encima de su límite)
        size = 5 * 1024 * 1024
        w = x_owner_hold(f"head -c {size} /dev/zero | tr '\\0' 'x'", hold=90)

        got = get_clip() or ""
        check("X→Windows 5 MB", len(got) == size, f"recibidos {len(got)}")
        w.kill()

        # 3) 20 MB Windows→X (supera una petición: Xming envía con INCR)
        big = "y" * (20 * 1024 * 1024)
        set_clip(big)
        time.sleep(1)
        out = wsl(f"{ENV} timeout 60 xclip -o -selection clipboard | wc -c", timeout=90).strip()
        check("Windows→X 20 MB (INCR)", out == str(len(big)), f"recibidos {out}")
    finally:
        stop(srv)
        wsl("pkill xclip; true")

    # 4) -noprimary: seleccionar en X (PRIMARY) no cambia el portapapeles de Windows
    srv = start(["-noprimary"])
    try:
        set_clip("intacto")
        w = x_owner_hold("printf 'seleccion primaria'", selection="primary", expect_windows_change=False)

        got = get_clip()
        check("-noprimary: PRIMARY no pisa el portapapeles", got == "intacto", repr(got))
        w.kill()
        w = x_owner_hold("printf 'desde clipboard'")

        got = get_clip()
        check("-noprimary: CLIPBOARD sigue funcionando", got == "desde clipboard", repr(got))
        w.kill()
    finally:
        stop(srv)
        wsl("pkill xclip; true")

    # 5) -noclipboard: no hay integración
    srv = start(["-noclipboard"])
    try:
        set_clip("solo windows")
        time.sleep(1)
        out = wsl(f"{ENV} timeout 5 xclip -o -selection clipboard 2>&1")
        check("-noclipboard: X no ve el portapapeles de Windows", "solo windows" not in out, repr(out[:60]))
        with open(LOG, encoding="latin-1") as f:
            log = f.read()
        check("-noclipboard: no arranca el hilo del clipboard", "winClipboardProc - Hello" not in log)
    finally:
        stop(srv)

    # 6) Listener moderno en uso (log de la primera ejecución se sobrescribe: relanzar)
    srv = start([])
    try:
        with open(LOG, encoding="latin-1") as f:
            log = f.read()
        check("usa AddClipboardFormatListener", "using AddClipboardFormatListener" in log)
        check("sin 'XConvertSelection () failed' en el log", "XConvertSelection () failed" not in log)
    finally:
        stop(srv)
finally:
    set_clip(original)
    wsl(f"xauth remove {host}:{DISP}; pkill xclip; true")
    os.remove(AUTH)
    os.rmdir(TMP)

print(f"\n{sum(ok for _, ok in results)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

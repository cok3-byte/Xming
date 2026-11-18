"""Pruebas de las mejoras tomadas de XmingNotes (servidor y XLaunch) desde Windows y WSL.

Uso (con Xming y XLaunch compilados en dist/):
    python -I winbuild/tests/xltest.py dist [display]

Requisitos: distro WSL "Ubuntu-24.04" con x11-apps, x11-utils y xauth; el Firewall
de Windows debe permitir dist/Xming.exe. Las pruebas de XLaunch arrancan Xming en
displays libres por encima de 20 y lo cierran al terminar; las que esperan un
mensaje de error cierran XLaunch con el mensaje abierto.

Cubre: rechazo de clientes con el otro orden de bytes (+byteswappedclients),
versión de Windows y proveedor en el log, -hostintitle, COPYING.txt en dist/, y en
XLaunch: display automático, display inválido u ocupado, que Xming siga abierto al
terminar el programa, búsqueda de .xlaunch en %APPDATA%\\Xming y la contraseña de
plink entre comillas.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
DIST = os.path.abspath(sys.argv[1])
DISP = sys.argv[2] if len(sys.argv) > 2 else "5"
DISTRO = "Ubuntu-24.04"
u32 = ctypes.WinDLL("user32", use_last_error=True)
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")


def wsl(cmd, timeout=60, background=False):
    args = ["wsl", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", cmd]
    if background:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def processes(names):
    flt = " OR ".join(f"Name='{n}'" for n in names)
    ps = (f"Get-CimInstance Win32_Process -Filter \"{flt}\" | "
          "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    if not out.strip():
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def children(parent, names, timeout, want=1):
    """Procesos hijos de `parent` con nombre en `names`, esperando hasta `timeout`."""
    end = time.time() + timeout
    found = []
    while time.time() < end:
        found = [p for p in processes(names) if p["ParentProcessId"] == parent]
        if len(found) >= want:
            break
        time.sleep(0.5)
    return found


def kill(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def listening(n):
    try:
        with socket.create_connection(("127.0.0.1", 6000 + n), timeout=1):
            return True
    except OSError:
        return False


def pad(b):
    return b + b"\0" * (-len(b) % 4)


def x_setup(order, cookie=None):
    """Establecimiento de conexión X con orden de bytes 'l' o 'B': (éxito, motivo)."""
    fmt = "<" if order == "l" else ">"
    name, data = (b"MIT-MAGIC-COOKIE-1", cookie) if cookie else (b"", b"")
    req = struct.pack(fmt + "cxHHHH2x", order.encode(), 11, 0, len(name), len(data)) + pad(name) + pad(data)
    with socket.create_connection(("127.0.0.1", 6000 + int(DISP)), timeout=5) as s:
        s.sendall(req)
        head = b""
        while len(head) < 8:
            chunk = s.recv(8 - len(head))
            if not chunk:
                break
            head += chunk
        if len(head) < 8:
            return None, "sin respuesta"
        success, reason_len = head[0], head[1]
        reason = s.recv(reason_len).decode("latin-1") if success == 0 else ""
        return success, reason


def write_xlaunch(path, **attrs):
    base = {"WindowMode": "MultiWindow", "ClientMode": "NoClient", "Display": "21", "Clipboard": "true"}
    base.update(attrs)
    body = " ".join(f'{k}="{v}"' for k, v in base.items())
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<XLaunch xmlns="http://www.straightrunning.com/XmingNotes" {body}/>\n')


def xlaunch(cfg, cwd):
    return subprocess.Popen([os.path.join(DIST, "XLaunch.exe"), "-run", cfg], cwd=cwd)


EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def window_titles(pid):
    titles = []

    def cb(hwnd, _):
        owner = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            u32.GetWindowTextW(hwnd, buf, 512)
            titles.append(buf.value)
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return titles


def find_title(pid, prefix, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for t in window_titles(pid):
            if t.startswith(prefix):
                return t
        time.sleep(0.3)
    return None


host = wsl("ip route show default | cut -d' ' -f3").strip()
wslhost = wsl("hostname").strip()
TMP = tempfile.mkdtemp(prefix="xltest-")
AUTH = os.path.join(TMP, "Xauthority")
cookie = secrets.token_bytes(16)


def field(b):
    return struct.pack(">H", len(b)) + b


with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP};"


def server(extra, log=None):
    out = open(log, "wb") if log else subprocess.DEVNULL
    p = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow", "-auth", AUTH, *extra],
                         cwd=DIST, stdout=out, stderr=out)
    time.sleep(5)
    return p


APPDATA_CFG = os.path.join(os.environ["APPDATA"], "Xming", "xltest-probe.xlaunch")
made_appdata_dir = not os.path.isdir(os.path.dirname(APPDATA_CFG))

try:
    # --- Servidor ---
    errlog = os.path.join(TMP, "xming-stderr.txt")
    srv = server(["-hostintitle"], errlog)
    try:
        ok, reason = x_setup("l", cookie)
        check("cliente del mismo orden de bytes aceptado", ok == 1, f"respuesta={ok} {reason}")
        ok, reason = x_setup("B", cookie)
        check("cliente big-endian rechazado por defecto", ok == 0 and "endianess" in reason,
              f"respuesta={ok} {reason!r}")
        info = wsl(f"{ENV} xdpyinfo | grep 'vendor string'")
        check("vendor string identifica el fork", "Unofficial Xming fork" in info, info.strip())
        # WSL usa por defecto el nombre de equipo de Windows: para simular un
        # cliente remoto, xclock corre en un espacio UTS con otro nombre.
        bg = wsl(f"{ENV} unshare -u sh -c 'hostname xltest-remote; xclock -title xltest-probe'",
                 background=True)
        t = find_title(srv.pid, "xltest-probe")
        check("-hostintitle añade @equipo a clientes remotos",
              t == "xltest-probe @ xltest-remote", repr(t))
        bg2 = wsl(f"{ENV} xclock -title xltest-local", background=True)
        t = find_title(srv.pid, "xltest-local")
        check("-hostintitle no lo añade si el cliente es del mismo equipo",
              t == "xltest-local", f"{t!r} (WSL: {wslhost})")
        wsl("pkill xclock; true")
        bg.wait(timeout=10)
        bg2.wait(timeout=10)
    finally:
        srv.kill()
        srv.wait()
        time.sleep(1)
    log = open(errlog, encoding="latin-1").read()
    m = re.search(r"^OS: (Windows \S+) \((\d+\.\d+\.\d+)\)", log, re.M)
    check("el log registra la versión real de Windows", m is not None and m.group(1) != "Vista",
          m.group(0) if m else "")
    check("el log da el contacto del fork",
          "github.com/cok3-byte/Xming/issues" in log, "")

    srv = server(["+byteswappedclients"])
    try:
        ok, reason = x_setup("B", cookie)
        check("+byteswappedclients acepta clientes big-endian", ok == 1, f"respuesta={ok} {reason!r}")
    finally:
        srv.kill()
        srv.wait()
        time.sleep(1)

    srv = server([])
    try:
        bg = wsl(f"{ENV} xclock -title xltest-plain", background=True)
        t = find_title(srv.pid, "xltest-plain")
        check("sin -hostintitle el título no cambia", t == "xltest-plain", repr(t))
        wsl("pkill xclock; true")
        bg.wait(timeout=10)

        # --- XLaunch con un servidor ya en marcha en DISP ---
        cfg = os.path.join(TMP, "busy.xlaunch")
        write_xlaunch(cfg, Display=DISP, ClientMode="StartProgram", ClientStart="Local",
                      Program="cmd /c exit")
        xl = xlaunch(cfg, TMP)
        found = children(xl.pid, ["Xming.exe", "cmd.exe"], 6)
        check("XLaunch no arranca nada si el display está ocupado", not found and xl.poll() is None,
              str([p["Name"] for p in found]))
        kill(xl.pid)
    finally:
        srv.kill()
        srv.wait()
        time.sleep(1)

    # --- Display inválido en el .xlaunch ---
    cfg = os.path.join(TMP, "bad.xlaunch")
    write_xlaunch(cfg, Display="21 -ac")
    xl = xlaunch(cfg, TMP)
    found = children(xl.pid, ["Xming.exe"], 6)
    check("XLaunch rechaza un display que no es un número",
          not found, found[0]["CommandLine"] if found else "")
    kill(xl.pid)
    for p in found:
        kill(p["ProcessId"])

    # --- Display automático ---
    expected = next(n for n in range(64) if not listening(n))
    cfg = os.path.join(TMP, "auto.xlaunch")
    write_xlaunch(cfg, Display="")
    xl = xlaunch(cfg, TMP)
    found = children(xl.pid, ["Xming.exe"], 15)
    cmd = found[0]["CommandLine"] if found else ""
    check("Display vacío usa el primer display libre", re.search(rf'" :{expected} ', cmd) is not None,
          f"esperado :{expected}: {cmd}")
    for p in found:
        kill(p["ProcessId"])
    kill(xl.pid)
    time.sleep(1)

    # --- Xming sigue abierto cuando el programa termina ---
    cfg = os.path.join(TMP, "client.xlaunch")
    write_xlaunch(cfg, Display="22", ClientMode="StartProgram", ClientStart="Local",
                  Program="cmd /c exit")
    xl = xlaunch(cfg, TMP)
    found = children(xl.pid, ["Xming.exe"], 15)
    end = time.time() + 15
    while time.time() < end and not listening(22):
        time.sleep(0.3)
    time.sleep(5)  # cmd /c exit ya ha terminado
    alive = [p for p in processes(["Xming.exe"]) if p["ParentProcessId"] == xl.pid]
    check("Xming sigue abierto cuando termina el programa", bool(alive) and listening(22),
          f"Xming hijos={len(alive)}")
    check("XLaunch espera a Xming mientras sigue abierto", xl.poll() is None, "")
    for p in alive or found:
        kill(p["ProcessId"])
    try:
        xl.wait(timeout=10)
        check("XLaunch termina cuando se cierra Xming", True)
    except subprocess.TimeoutExpired:
        check("XLaunch termina cuando se cierra Xming", False)
        kill(xl.pid)
    time.sleep(1)

    # --- .xlaunch buscado en %APPDATA%\Xming, con nombre sin extensión ---
    os.makedirs(os.path.dirname(APPDATA_CFG), exist_ok=True)
    write_xlaunch(APPDATA_CFG, Display="23")
    xl = subprocess.Popen([os.path.join(DIST, "XLaunch.exe"), "-run", "xltest-probe"], cwd=TMP)
    found = children(xl.pid, ["Xming.exe"], 15)
    cmd = found[0]["CommandLine"] if found else ""
    check("-run encuentra el .xlaunch en %APPDATA%\\Xming", '" :23 ' in cmd, cmd)
    for p in found:
        kill(p["ProcessId"])
    kill(xl.pid)
    time.sleep(1)

    # --- plink: contraseña con espacios y comillas, entre comillas ---
    # Un cmd.exe copiado como plink.exe se queda abierto (oculto) y deja leer su
    # línea de comandos sin conectar a ningún sitio.
    fake = os.path.join(TMP, "fakeputty")
    os.makedirs(fake)
    shutil.copy(os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), os.path.join(fake, "plink.exe"))
    cfg = os.path.join(TMP, "plink.xlaunch")
    write_xlaunch(cfg, Display="24", ClientMode="StartProgram", ClientStart="PuTTY",
                  PathToProtocol=fake + "\\", RemoteHost="192.0.2.1", RemoteUser="prueba",
                  Program="xterm", PW='a b&quot;c\\')
    xl = xlaunch(cfg, TMP)
    found = children(xl.pid, ["plink.exe"], 20)
    cmd = found[0]["CommandLine"] if found else ""
    check("plink recibe la contraseña entre comillas", '-pw "a b\\"c\\\\" ' in cmd, cmd)
    for p in children(xl.pid, ["Xming.exe", "plink.exe"], 1, want=2):
        kill(p["ProcessId"])
    kill(xl.pid)

    # --- Licencia en dist/ ---
    copying = os.path.join(DIST, "COPYING.txt")
    text = open(copying, encoding="ascii", errors="replace").read() if os.path.exists(copying) else ""
    check("dist/COPYING.txt con la licencia del fork y las de terceros",
          "MIT License" in text and "Third-party notices" in text and "FreeType License" in text
          and "�" not in text, f"{len(text)} caracteres")
finally:
    wsl(f"pkill xclock; xauth remove {host}:{DISP}; true")
    if os.path.exists(APPDATA_CFG):
        os.remove(APPDATA_CFG)
        if made_appdata_dir:
            os.rmdir(os.path.dirname(APPDATA_CFG))
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

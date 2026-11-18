"""Pruebas de integración con el escritorio (modo -multiwindow) contra clientes reales en WSL.

Uso (desde Windows, con Xming compilado en dist/):
    python -I winbuild/tests/desktest.py dist [display]

Requisitos:
  - Distro de WSL "Ubuntu-24.04" con x11-apps, x11-utils, xauth y wmctrl.
  - El Firewall de Windows debe permitir la entrada a dist/Xming.exe desde la red de WSL.

Cubre: títulos Unicode (_NET_WM_NAME), rueda horizontal (botones 6/7) y botones
laterales (8/9), DPI del sistema, y _NET_WM_STATE (maximizar, encima, pantalla
completa), y que Xming arranca sin ventana de consola (también la de xkbcomp). La prueba
de ratón mueve el cursor un momento y lo devuelve a su sitio.
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
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
u32 = ctypes.WinDLL("user32", use_last_error=True)
gdi = ctypes.WinDLL("gdi32")
results = []


def wsl(cmd, timeout=60, background=False):
    args = ["wsl", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", cmd]
    if background:
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")


# --- ventanas Win32 del proceso Xming ---
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def xming_windows(pid):
    found = []

    def cb(hwnd, _):
        owner = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(hwnd, cls, 256)
            if cls.value.endswith(" X"):
                found.append(hwnd)
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return found


def title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def find_window(pid, pattern, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for h in xming_windows(pid):
            if re.search(pattern, title(h)):
                return h
        time.sleep(0.2)
    return None


def rect(hwnd):
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


# --- servidor y cookie ---
host = wsl("ip route show default | cut -d' ' -f3").strip()
TMP = tempfile.mkdtemp(prefix="desktest-")
AUTH = os.path.join(TMP, "Xauthority")
cookie = secrets.token_bytes(16)


def field(b):
    return struct.pack(">H", len(b)) + b


with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP};"

srv = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow", "-auth", AUTH],
                       cwd=DIST, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pid = srv.pid
time.sleep(5)
clients = []
try:
    # 1) DPI: X debe ver el DPI del sistema (Xming es DPI-aware)
    hdc = u32.GetDC(None)
    sys_dpi = gdi.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    u32.ReleaseDC(None, hdc)
    info = wsl(f"{ENV} xdpyinfo | grep -E 'dimensions|resolution'")
    m = re.search(r"resolution:\s+(\d+)x(\d+)", info)
    xdpi = int(m.group(1)) if m else None
    check("DPI de X = DPI del sistema", xdpi == sys_dpi, f"X={xdpi} Windows={sys_dpi}")
    d = re.search(r"dimensions:\s+(\d+)x(\d+)", info)
    vw, vh = u32.GetSystemMetrics(78), u32.GetSystemMetrics(79)  # SM_CXVIRTUALSCREEN
    check("pantalla X = escritorio en píxeles reales",
          d and (int(d.group(1)), int(d.group(2))) == (vw, vh),
          f"X={d.group(1)}x{d.group(2) if d else '?'} Windows={vw}x{vh}")

    # 2) EWMH anunciado
    root = wsl(f"{ENV} xprop -root _NET_SUPPORTED _NET_SUPPORTING_WM_CHECK")
    check("_NET_SUPPORTED anuncia _NET_WM_STATE_FULLSCREEN", "_NET_WM_STATE_FULLSCREEN" in root)
    check("_NET_SUPPORTING_WM_CHECK presente", "window id" in root)

    # 3) Título Unicode vía _NET_WM_NAME
    clients.append(wsl(f"{ENV} xclock -geometry 220x220+60+60 -name relojtest; sleep 300", background=True))
    h = find_window(pid, r"^relojtest$|^xclock$")
    check("xclock aparece como ventana Windows", h is not None)
    xid = wsl(f"{ENV} xwininfo -name relojtest 2>/dev/null | sed -n 's/.*Window id: \\(0x[0-9a-f]*\\).*/\\1/p'").strip() \
        or wsl(f"{ENV} xwininfo -name xclock | sed -n 's/.*Window id: \\(0x[0-9a-f]*\\).*/\\1/p'").strip()
    texto = "Título ñandú € 日本語"
    wsl(f"{ENV} xprop -id {xid} -f _NET_WM_NAME 8u -set _NET_WM_NAME '{texto}'")
    ok = wait_for(lambda: title(h) == texto) if h else False
    check("título Unicode (_NET_WM_NAME)", ok, repr(title(h)) if h else "")

    # 4) _NET_WM_STATE vía wmctrl
    if h:
        wsl(f"{ENV} wmctrl -i -r {xid} -b add,maximized_vert,maximized_horz")
        check("maximizar (_NET_WM_STATE)", wait_for(lambda: u32.IsZoomed(h)))
        st = wsl(f"{ENV} xprop -id {xid} _NET_WM_STATE")
        check("el WM refleja el estado en la propiedad", "MAXIMIZED_VERT" in st, st.strip())
        wsl(f"{ENV} wmctrl -i -r {xid} -b remove,maximized_vert,maximized_horz")
        check("restaurar", wait_for(lambda: not u32.IsZoomed(h)))

        GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x8
        u32.GetWindowLongW.restype = ctypes.c_long
        wsl(f"{ENV} wmctrl -i -r {xid} -b add,above")
        check("siempre encima (ABOVE)", wait_for(lambda: u32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOPMOST))
        wsl(f"{ENV} wmctrl -i -r {xid} -b remove,above")
        check("quitar siempre encima", wait_for(lambda: not (u32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOPMOST)))

        before = rect(h)
        wsl(f"{ENV} wmctrl -i -r {xid} -b add,fullscreen")

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        u32.MonitorFromWindow.restype = ctypes.c_void_p
        u32.GetMonitorInfoW(ctypes.c_void_p(u32.MonitorFromWindow(h, 2)), ctypes.byref(mi))
        mon = (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
        check("pantalla completa ocupa el monitor", wait_for(lambda: rect(h) == mon), f"{rect(h)} vs {mon}")
        wsl(f"{ENV} wmctrl -i -r {xid} -b remove,fullscreen")
        check("salir de pantalla completa recupera el tamaño", wait_for(lambda: rect(h) == before),
              f"{rect(h)} vs {before}")

    # 5) Ratón: rueda horizontal -> 6/7 y botones laterales -> 8/9
    xev = wsl(f"{ENV} stdbuf -oL timeout 25 xev -geometry 300x300+300+200 -name xevtest -event button", background=True)
    hx = find_window(pid, r"xevtest|Event Tester")
    if hx:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        old = POINT()
        u32.GetCursorPos(ctypes.byref(old))
        l, t, r_, b = rect(hx)
        u32.SetForegroundWindow(hx)
        u32.SetCursorPos((l + r_) // 2, (t + b) // 2)
        time.sleep(0.5)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wt.DWORD),
                        ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wt.DWORD), ("mi", MOUSEINPUT)]  # 40 bytes en x64: sin relleno extra

        def send(flags, data=0):
            inp = INPUT(type=0, mi=MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0))
            u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.15)

        MOUSEEVENTF_HWHEEL, MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP = 0x1000, 0x0080, 0x0100
        send(MOUSEEVENTF_HWHEEL, 120)    # derecha -> botón 7
        send(MOUSEEVENTF_HWHEEL, -120)   # izquierda -> botón 6
        send(MOUSEEVENTF_XDOWN, 1)
        send(MOUSEEVENTF_XUP, 1)         # XBUTTON1 -> botón 8
        u32.SetCursorPos(old.x, old.y)
        time.sleep(1)
        wsl("pkill xev; true")
        out = xev.communicate(timeout=30)[0].decode("utf-8", "replace")
        buttons = [int(x) for x in re.findall(r"ButtonPress.*?button (\d+)", out, re.S)]
        check("rueda horizontal: derecha = botón 7, izquierda = botón 6", buttons[:2] == [7, 6], str(buttons))
        check("botón lateral XBUTTON1 = botón 8", 8 in buttons, str(buttons))
    else:
        check("xev aparece como ventana Windows", False)
finally:
    for c in clients:
        c.kill()
    wsl(f"pkill xclock; pkill xev; true")
    srv.kill()
    srv.wait()
    time.sleep(1)


# 6) Sin ventana de consola: Xming es una aplicación de ventanas y xkbcomp, que lanza
# al arrancar, no abre una consola propia.
XMING = os.path.join(DIST, "Xming.exe")
CONSOLE_CLASSES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS")


def pe_subsystem(path):
    with open(path, "rb") as f:
        head = f.read(4096)
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    return struct.unpack_from("<H", head, pe + 24 + 68)[0]  # IMAGE_OPTIONAL_HEADER.Subsystem


def console_windows():
    found = set()

    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        if cls.value in CONSOLE_CLASSES and u32.IsWindowVisible(hwnd):
            found.add(hwnd)
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return found


try:
    sub = pe_subsystem(XMING)
    check("Xming.exe es una aplicación de ventanas (subsistema GUI)", sub == 2, f"subsistema={sub}")
    r = subprocess.run([XMING, "-help"], capture_output=True, timeout=30, cwd=DIST)
    check("-help con stderr redirigido muestra el uso", b"-hostintitle" in r.stdout + r.stderr,
          f"{len(r.stdout + r.stderr)} bytes")

    # Arranque como desde el Explorador: sin redirigir nada.
    before = console_windows()
    srv = subprocess.Popen([XMING, f":{DISP}", "-multiwindow", "-auth", AUTH], cwd=DIST)
    new = set()
    end = time.time() + 8
    while time.time() < end:
        new |= console_windows() - before
        time.sleep(0.1)
    check("arrancar Xming no abre ninguna ventana de consola", not new, f"{len(new)} nuevas")
    info = wsl(f"{ENV} xdpyinfo | grep 'vendor string'")
    check("el servidor sin consola acepta clientes", "vendor string" in info, info.strip())
finally:
    srv.kill()
    wsl(f"xauth remove {host}:{DISP}; true")
    os.remove(AUTH)
    os.rmdir(TMP)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

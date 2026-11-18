"""Pruebas de la Fase 6 (rendimiento remoto y XLaunch) desde Windows y WSL.

Uso (con Xming y XLaunch compilados en dist/):
    python -I winbuild/tests/sshtest.py dist [display]

Requisitos: distro WSL "Ubuntu-24.04" con x11-apps, x11-utils y xauth; el Firewall
de Windows debe permitir dist/Xming.exe. La parte de XLaunch abre un momento una
consola de ssh hacia 192.0.2.1 (dirección de documentación, inalcanzable) para leer
la línea de comando con la que se lanza, y luego la cierra.
"""
import json
import os
import re
import secrets
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


def processes(names):
    """Procesos con nombre en `names`: pid, padre y línea de comando (vía CIM)."""
    flt = " OR ".join(f"Name='{n}'" for n in names)
    ps = (f"Get-CimInstance Win32_Process -Filter \"{flt}\" | "
          "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    if not out.strip():
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


host = wsl("ip route show default | cut -d' ' -f3").strip()
TMP = tempfile.mkdtemp(prefix="sshtest-")
AUTH = os.path.join(TMP, "Xauthority")
cookie = secrets.token_bytes(16)


def field(b):
    return struct.pack(">H", len(b)) + b


with open(AUTH, "wb") as f:
    f.write(struct.pack(">H", 0xFFFF) + field(b"") + field(DISP.encode())
            + field(b"MIT-MAGIC-COOKIE-1") + field(cookie))
wsl(f"xauth -q add {host}:{DISP} MIT-MAGIC-COOKIE-1 {cookie.hex()}")
ENV = f"export DISPLAY={host}:{DISP};"


def server(extra):
    p = subprocess.Popen([os.path.join(DIST, "Xming.exe"), f":{DISP}", "-multiwindow", "-auth", AUTH, *extra],
                         cwd=DIST, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    return p


def exposes_when_uncovered():
    """Expose que recibe una ventana al tapar y destapar otra encima de ella."""
    out = wsl(f"{ENV} stdbuf -oL timeout 12 xev -geometry 300x300+100+100 -event expose > /tmp/xev.txt & "
              "sleep 3; xclock -geometry 250x250+120+120 & sleep 3; pkill xclock; sleep 3; "
              "pkill xev; sleep 1; awk '/^Expose/{n++} END{print n+0}' /tmp/xev.txt; "
              "grep -c '' /tmp/xev.txt")
    nums = [int(x) for x in out.split()]
    return nums[0] if nums else -1


try:
    # --- Servidor ---
    srv = server([])
    try:
        info = wsl(f"{ENV} xdpyinfo")
        for ext in ("RENDER", "BIG-REQUESTS", "XC-MISC"):
            check(f"extensión {ext} activa", re.search(rf"^\s+{ext}\s*$", info, re.M) is not None)
        m = re.search(r"options:\s+backing-store (\w+)", info)
        check("backing store disponible por defecto", m and m.group(1) != "NO", m.group(0) if m else "")
        exp_default = exposes_when_uncovered()
    finally:
        srv.kill()
        time.sleep(1)
    srv = server(["-bs"])
    try:
        info = wsl(f"{ENV} xdpyinfo")
        m = re.search(r"options:\s+backing-store (\w+)", info)
        check("-bs desactiva el backing store", m and m.group(1) == "NO", m.group(0) if m else "")
        exp_bs = exposes_when_uncovered()
    finally:
        srv.kill()
        time.sleep(1)
    check("menos Expose al destapar con backing store", 0 <= exp_default < exp_bs,
          f"por defecto={exp_default} con -bs={exp_bs}")

    # --- XLaunch ---
    for compress in (True, False):
        cfg = os.path.join(TMP, "test.xlaunch")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<XLaunch xmlns="http://www.straightrunning.com/XmingNotes" '
                    'WindowMode="MultiWindow" ClientMode="StartProgram" ClientStart="OpenSSH" '
                    'Program="xterm" RemoteHost="192.0.2.1" RemoteUser="prueba" Display="9" '
                    f'Clipboard="true" Compress="{"true" if compress else "false"}"/>\n')
        xl = subprocess.Popen([os.path.join(DIST, "XLaunch.exe"), "-run", cfg], cwd=TMP)
        found = {}
        end = time.time() + 30
        while time.time() < end and len(found) < 2:
            for p in processes(["Xming.exe", "ssh.exe"]):
                if p["Name"] == "Xming.exe" and p["ParentProcessId"] == xl.pid:
                    found["xming"] = p
                if p["Name"] == "ssh.exe" and p["ParentProcessId"] == xl.pid:
                    found["ssh"] = p
            time.sleep(0.5)
        for p in found.values():
            subprocess.run(["taskkill", "/F", "/PID", str(p["ProcessId"])], capture_output=True)
        xl.kill()
        tag = "con compresión" if compress else "sin compresión"
        xcmd = found.get("xming", {}).get("CommandLine", "")
        scmd = found.get("ssh", {}).get("CommandLine", "")
        if compress:
            check("XLaunch lanza Xming.exe con ruta absoluta entre comillas",
                  xcmd.startswith(f'"{os.path.join(DIST, "Xming.exe")}"'), xcmd)
            check("XLaunch usa el OpenSSH de Windows con ruta absoluta",
                  re.match(r'^"[A-Za-z]:\\.*\\OpenSSH\\ssh\.exe" ', scmd, re.I) is not None, scmd)
        check(f"ssh {tag}: -C y ServerAliveInterval solo con compresión",
              (("-C " in scmd) and ("ServerAliveInterval=30" in scmd)) == compress and "-Y" in scmd, scmd)
        time.sleep(1)
finally:
    wsl(f"pkill xclock; pkill xev; xauth remove {host}:{DISP}; true")
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))
    os.rmdir(TMP)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} pruebas OK")
sys.exit(0 if all(ok for _, ok in results) else 1)

#!/usr/bin/env python3
"""Put every Iranian CIDR into Happ's global excludedRoutes.

    python happ_excluded.py apply     # write the list (Happ must be closed)
    python happ_excluded.py clear     # remove it
    python happ_excluded.py status    # how many are in force
    python happ_excluded.py extract   # rebuild iran_cidrs.txt from Happ's geoip.dat

This is the only layer that survives Happ's strict-route firewall: Happ injects
`ip_cidr -> direct` into its own tun config, so the packets never enter the tunnel.
Kernel routes (`iran_direct.py`) are ignored while that firewall is up.
"""
import ipaddress, json, os, subprocess, sys, winreg

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
CIDR_FILE = os.path.join(HERE, "iran_cidrs.txt")
KEY = r"Software\Happ\OrganizationDefaults\Preferences\AdvancedSettings"


def _happ_key(write=False):
    """HKCU\\Software\\Happ..., or the user's hive when running as SYSTEM."""
    access = winreg.KEY_READ | (winreg.KEY_SET_VALUE if write else 0)
    try:
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, access)
    except OSError:
        pass
    for i in range(winreg.QueryInfoKey(winreg.HKEY_USERS)[0]):
        sid = winreg.EnumKey(winreg.HKEY_USERS, i)
        if sid.endswith("_Classes"):
            continue
        try:
            return winreg.OpenKey(winreg.HKEY_USERS, sid + "\\" + KEY, 0, access)
        except OSError:
            continue
    raise SystemExit("Happ registry key not found -- is Happ installed for this user?")


def cidrs():
    with open(CIDR_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def current():
    try:
        k = _happ_key()
        raw, _ = winreg.QueryValueEx(k, "excludedRoutes")
    except (OSError, SystemExit):
        return []
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw) if raw.startswith("[") else [x for x in raw.splitlines() if x.strip()]
    except ValueError:
        return [x for x in raw.splitlines() if x.strip()]


def apply():
    if "yes" in subprocess.run(["powershell", "-NoProfile", "-Command",
                                "if (Get-Process Happ -ErrorAction SilentlyContinue) {'yes'}"],
                               capture_output=True, text=True).stdout:
        print("Happ is running -- close it first (it rewrites its settings on exit)")
        return 1
    items = cidrs()
    payload = json.dumps(items, separators=(",", ":"))
    k = _happ_key(write=True)
    winreg.SetValueEx(k, "excludedRoutes", 0, winreg.REG_SZ, payload)
    print("excludedRoutes  %d CIDRs written (%.0f KB)" % (len(items), len(payload) / 1024))
    return 0


def clear():
    try:
        k = _happ_key(write=True)
        winreg.DeleteValue(k, "excludedRoutes")
        print("excludedRoutes  removed")
    except OSError:
        print("excludedRoutes  was not set")


def status():
    n = len(current())
    total = len(cidrs())
    print("excludedRoutes  %d/%d Iranian CIDRs in force" % (n, total))
    print("cidr file       %s" % CIDR_FILE)


def extract():
    """Rebuild iran_cidrs.txt from Happ's Chocolate4U geoip.dat."""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Happ", "routing")
    found = None
    for root, _, files in os.walk(base):
        if "geoip.dat" in files and ("IRAN" in root.upper() or "IR-" in root.upper()):
            found = os.path.join(root, "geoip.dat")
            break
    if not found:
        raise SystemExit("geoip.dat not found under %s" % base)

    def varint(b, i):
        v = sh = 0
        while True:
            x = b[i]; i += 1
            v |= (x & 0x7F) << sh; sh += 7
            if not x & 0x80:
                return v, i

    b = open(found, "rb").read()
    i = 0; ir = []
    while i < len(b) and b[i] == 0x0A:
        i += 1; ln, i = varint(b, i)
        chunk = b[i:i + ln]; i += ln
        j = 0; code = None; nets = []
        while j < len(chunk):
            tag = chunk[j]; j += 1
            if tag == 0x0A:
                l, j = varint(chunk, j); code = chunk[j:j + l].decode(); j += l
            elif tag == 0x12:
                l, j = varint(chunk, j); sub = chunk[j:j + l]; j += l
                k2 = 0; ipb = pfx = None
                while k2 < len(sub):
                    t = sub[k2]; k2 += 1
                    if t == 0x0A:
                        il, k2 = varint(sub, k2); ipb = sub[k2:k2 + il]; k2 += il
                    elif t == 0x10:
                        pfx, k2 = varint(sub, k2)
                    else:
                        break
                if ipb and pfx is not None and len(ipb) == 4:
                    nets.append(ipaddress.ip_network("%s/%d" % (ipaddress.IPv4Address(ipb), pfx), strict=False))
            else:
                break
        if code == "IR":
            ir = nets
    if not ir:
        raise SystemExit("no IR entries in %s" % found)
    with open(CIDR_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(str(n) for n in ir) + "\n")
    print("extracted       %d Iranian IPv4 blocks -> %s" % (len(ir), CIDR_FILE))


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = {"apply": apply, "clear": clear, "status": status, "extract": extract}.get(action)
    sys.exit(fn() if fn else __doc__)

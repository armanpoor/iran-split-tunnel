#!/usr/bin/env python3
"""Point Happ's routing profiles at DNS servers that can answer Iranian names.

Why this is the real fix
------------------------
Happ's Xray TUN takes over DNS completely. With the stock profile, `.ir` names fail
because the tunnel asks a foreign DoH resolver (Cloudflare) and gets NXDOMAIN --
measured: `1.1.1.1` and `8.8.8.8` return NXDOMAIN for `varzesh3.com` while
`217.218.155.155` returns real A records.

Measured on Happ 4.7.2 / Xray TUN (41-site survey, tunnel genuinely up):

    domesticDnsIp   remoteDns        fakeDns   Iranian sites OK
    195.168.1.1     1.1.1.1/DoH      true      5/41     (stock, dead resolver)
    217.218.155.155 1.1.1.1/DoH      false     30/41    <- this script
    217.218.155.155 217.218.155.155  false     6/41     (resolver itself routed into the tunnel)

The remaining 11 failures were verified to fail with the tunnel OFF too -- they are
blocked by the ISP, not by the tunnel. Compare `python happ_dns.py baseline`.

    python happ_dns.py apply      # write the working combination (Happ must be closed)
    python happ_dns.py status
    python happ_dns.py restore    # back to the stock profile values
"""
import json, os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH = os.path.join(os.environ["LOCALAPPDATA"], "Happ", "routing.json")

DOMESTIC = "217.218.155.155"   # answers .ir and foreign alike, reachable from Iran
REMOTE = "1.1.1.1"             # stays foreign: if the resolver itself is Iranian,
REMOTE_TYPE = "DoH"            # Happ routes the resolver into the tunnel and everything breaks
REMOTE_DOMAIN = "https://cloudflare-dns.com/dns-query"

STOCK = {
    "domesticDnsIp": "195.168.1.1",
    "domesticDnsType": "DoU",
    "domesticDnsDomain": "",
    "remoteDnsIp": "1.1.1.1",
    "remoteDnsType": "DoH",
    "remoteDnsDomain": "https://cloudflare-dns.com/dns-query",
    "fakeDns": True,
}


def happ_running():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "if (Get-Process Happ -ErrorAction SilentlyContinue) {'yes'}"],
                       capture_output=True, text=True)
    return "yes" in r.stdout


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(d):
    shutil.copy2(PATH, PATH + ".bak")
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def apply():
    if happ_running():
        sys.exit("Happ is running -- close it first, it rewrites routing.json on exit.")
    d = load()
    for r in d.get("routings", []):
        r["domesticDnsIp"] = DOMESTIC
        r["domesticDnsType"] = "DoU"
        r["domesticDnsDomain"] = ""
        r["remoteDnsIp"] = REMOTE
        r["remoteDnsType"] = REMOTE_TYPE
        r["remoteDnsDomain"] = REMOTE_DOMAIN
        r["fakeDns"] = False
        r["domainStrategy"] = "IPIfNonMatch"
        print("patched %-34s domestic=%s remote=%s/%s fakeDns=False"
              % (r["name"].encode("ascii", "replace").decode(), DOMESTIC, REMOTE, REMOTE_TYPE))
    save(d)


def restore():
    if happ_running():
        sys.exit("Happ is running -- close it first.")
    d = load()
    for r in d.get("routings", []):
        r.update(STOCK)
        print("restored %s" % r["name"].encode("ascii", "replace").decode())
    save(d)


def status():
    d = load()
    print("%-34s %-16s %-18s %-8s" % ("profile", "domestic", "remote", "fakeDns"))
    for r in d.get("routings", []):
        print("%-34s %-16s %-18s %-8s"
              % (r["name"].encode("ascii", "replace").decode(),
                 r.get("domesticDnsIp"), "%s/%s" % (r.get("remoteDnsIp"), r.get("remoteDnsType")),
                 r.get("fakeDns")))
    ok = all(r.get("domesticDnsIp") == DOMESTIC and r.get("fakeDns") is False
             for r in d.get("routings", []))
    print()
    print("working combination applied: %s" % ("yes" if ok else "NO -- run apply"))


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"apply": apply, "restore": restore, "status": status}.get(action, status)()

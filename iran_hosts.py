#!/usr/bin/env python3
"""Pin a short list of Iranian domains into the hosts file.

Use this **only** for the few names Happ's DNS still fails on. The main fix is
`happ_dns.py`; this is a scalpel, not a net.

Why it must stay short: Windows resolves through the hosts file linearly. Measured on
Windows 11 -- 5,000 entries made every lookup take 5.6 s, 20,000 timed out entirely.
So do NOT try to pin the whole `.ir` zone here; it makes the machine unusable.

    python iran_hosts.py apply      # resolve + write (needs admin, hosts is read-only)
    python iran_hosts.py status
    python iran_hosts.py clear
"""
import json, os, random, socket, struct, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "drivers", "etc", "hosts")
MARK_BEGIN = "# >>> iran-split-tunnel (managed) >>>"
MARK_END = "# <<< iran-split-tunnel (managed) <<<"

IR_DNS = [("217.218.155.155", 53), ("217.218.127.127", 53), ("185.51.200.2", 53)]

# Names to pin. Happ's DNS does not answer these while the tunnel is up, so the address
# is written here instead. Keep the list small -- the hosts file is scanned linearly
# (5k entries -> 5.6s per lookup). Add only what you actually visit.
NAMES = [
    # measured failing with the tunnel up, working without it
    "adliran.ir", "www.adliran.ir",
    "iribnews.ir", "www.iribnews.ir",
    "cafebazaar.ir", "www.cafebazaar.ir",
    "zoomit.ir", "www.zoomit.ir",
    "sampad.ir", "www.sampad.ir",
    "irimo.ir", "www.irimo.ir",
    # everyday sites: pinning them removes any dependence on the tunnel's DNS
    "varzesh3.com", "www.varzesh3.com",
    "avalai.ir", "api.avalai.ir",
    "sso.my.gov.ir", "my.gov.ir",
    "digikala.com", "www.digikala.com",
    "irna.ir", "www.irna.ir",
    "isna.ir", "www.isna.ir",
    "yjc.ir", "www.yjc.ir",
    "mehrnews.com", "www.mehrnews.com",
    "khabaronline.ir", "www.khabaronline.ir",
    "hamshahrionline.ir", "www.hamshahrionline.ir",
    "tabnak.ir", "www.tabnak.ir",
    "shad.ir", "www.shad.ir",
    "aparat.com", "www.aparat.com",
    "divar.ir", "www.divar.ir",
    "torob.com", "www.torob.com",
    "sheypoor.com", "www.sheypoor.com",
    "filimo.com", "www.filimo.com",
    "shaparak.ir", "www.shaparak.ir",
    "snapp.ir", "www.snapp.ir",
]


def query(name, server, timeout=1.5):
    tid = random.randint(0, 65535)
    qn = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    pkt = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0) + qn + struct.pack("!HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (server, 53))
        data, _ = s.recvfrom(4096)
    except OSError:
        return []
    finally:
        s.close()
    an = struct.unpack("!H", data[6:8])[0]
    if not an:
        return []
    i = 12
    while i < len(data) and data[i]:
        i += data[i] + 1
    i += 5
    out = []
    for _ in range(an):
        if i + 10 > len(data):
            break
        if data[i] & 0xC0 == 0xC0:
            i += 2
        else:
            while i < len(data) and data[i]:
                i += data[i] + 1
            i += 1
        if i + 10 > len(data):
            break
        rtype = struct.unpack("!H", data[i:i + 2])[0]
        rdlen = struct.unpack("!H", data[i + 8:i + 10])[0]
        i += 10
        if rtype == 1 and rdlen == 4:
            out.append(socket.inet_ntoa(data[i:i + 4]))
        i += rdlen
    return out


def resolve(name):
    for host, _ in IR_DNS:
        ips = query(name, host)
        if ips:
            return ips
    return []


def read_hosts():
    try:
        return open(HOSTS, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def strip_block(text):
    out, skip = [], False
    for line in text.splitlines():
        s = line.strip()
        if s == MARK_BEGIN:
            skip = True
            continue
        if s == MARK_END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def existing_block():
    out, inside = {}, False
    for line in read_hosts().splitlines():
        s = line.strip()
        if s == MARK_BEGIN:
            inside = True
            continue
        if s == MARK_END:
            break
        if inside and s and not s.startswith("#"):
            parts = s.split()
            if len(parts) == 2:
                out.setdefault(parts[1], []).append(parts[0])
    return out


def apply():
    if len(NAMES) > 2000:
        sys.exit("NAMES has %d entries -- the hosts file does not scale that far "
                 "(5k entries -> 5.6s per lookup). Use happ_dns.py instead." % len(NAMES))
    known = existing_block()
    fresh = kept = 0
    lines = []
    for name in dict.fromkeys(NAMES):
        ips = resolve(name)
        if ips:
            fresh += 1
        else:
            ips = known.get(name, [])
            if ips:
                kept += 1
        for ip in ips[:2]:
            lines.append("%-16s %s" % (ip, name))
    if not lines:
        print("nothing resolved and no previous entries -- hosts left unchanged")
        return 1
    text = strip_block(read_hosts())
    block = [MARK_BEGIN] + lines + [MARK_END]
    open(HOSTS, "w", encoding="utf-8", newline="\n").write(text + "\n".join(block) + "\n")
    print("hosts: %d entries (%d fresh, %d kept) for %d names"
          % (len(lines), fresh, kept, len(dict.fromkeys(NAMES))))
    return 0


def clear():
    open(HOSTS, "w", encoding="utf-8", newline="\n").write(strip_block(read_hosts()))
    print("hosts: block removed")


def status():
    pinned = existing_block()
    print("hosts:      %s" % HOSTS)
    print("pinned:     %d names" % len(pinned))
    for name in dict.fromkeys(NAMES):
        print("  %-24s %s" % (name, ", ".join(pinned.get(name, ["not pinned"]))))


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    {"apply": apply, "clear": clear, "status": status}.get(action, status)()

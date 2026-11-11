"""Resolve Iranian domains via a working resolver and pin them in the hosts file.

Windows' resolver is hijacked by Happ's WFP filters while the tunnel is up, but raw
UDP/53 to 217.218.155.155 still answers. So: query it ourselves, write the answers
into the hosts file, and the browser never needs a DNS lookup for those names.

    python _hosts.py apply     # add/refresh the block
    python _hosts.py clear     # remove it
"""
import os, random, socket, struct, sys

MARK_BEGIN = "# >>> iran-direct (managed) >>>"
MARK_END = "# <<< iran-direct (managed) <<<"
HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "drivers", "etc", "hosts")
RESOLVERS = ["217.218.155.155", "185.51.200.2", "217.218.127.127"]
NAMES = [
    "varzesh3.com", "www.varzesh3.com", "api.avalai.ir", "avalai.ir",
    "sso.my.gov.ir", "my.gov.ir", "digikala.com", "www.digikala.com",
    "aparat.com", "www.aparat.com", "divar.ir", "www.divar.ir",
    "torob.com", "www.torob.com", "sheypoor.com", "www.sheypoor.com",
    "cafebazaar.ir", "shaparak.ir", "www.shaparak.ir", "bmi.ir", "www.bmi.ir",
    "snapp.ir", "www.snapp.ir", "digikala.com", "www.digikala.com",
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
    # walk past the question, then read A records
    i = 12
    while data[i] != 0:
        i += data[i] + 1
    i += 5
    out = []
    for _ in range(an):
        if i >= len(data):
            break
        while i < len(data) and data[i] & 0xC0 == 0xC0:
            i += 2
            break
        else:
            while i < len(data) and data[i] != 0:
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
    for srv in RESOLVERS:
        ips = query(name, srv)
        if ips:
            return ips
    return []


def resolve_many(names, workers=12, budget=6.0):
    """Resolve names in parallel with a hard overall deadline.

    Serial resolution is what made the script hang for minutes while the tunnel was
    up (23 names x 3 resolvers x 3s timeout). A short budget also keeps the scheduled
    task from piling up runs.
    """
    from concurrent.futures import ThreadPoolExecutor, wait
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(resolve, n): n for n in names}
        done, _ = wait(futs, timeout=budget)
        for fut in done:
            try:
                out[futs[fut]] = fut.result()
            except Exception:
                out[futs[fut]] = []
    return out


def strip(text):
    out, skip = [], False
    for line in text.splitlines():
        if line.strip() == MARK_BEGIN:
            skip = True
            continue
        if line.strip() == MARK_END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def existing():
    """Names already pinned in the managed block -> {name: [ips]}."""
    out = {}
    try:
        text = open(HOSTS, encoding="utf-8", errors="replace").read()
    except OSError:
        return out
    inside = False
    for line in text.splitlines():
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
    # Never let a failed lookup wipe a working block: keep what is already pinned and
    # only replace it when a fresh answer actually arrives. While the tunnel is up a
    # resolver can return nothing, and rewriting the block empty is what broke access
    # a few minutes after a good run.
    known = existing()
    text = strip(open(HOSTS, encoding="utf-8", errors="replace").read())
    wanted = list(dict.fromkeys(NAMES))
    answers = resolve_many(wanted)
    lines, fresh, kept = [], 0, 0
    for name in wanted:
        ips = answers.get(name) or []
        if ips:
            fresh += 1
        else:
            ips = known.get(name, [])
            if ips:
                kept += 1
        for ip in ips[:2]:
            lines.append("%-16s %s" % (ip, name))
    if not lines:
        print("hosts: no answers and nothing cached -- left unchanged")
        return 1
    block = [MARK_BEGIN] + lines + [MARK_END]
    open(HOSTS, "w", encoding="utf-8", newline="\n").write(text + "\n".join(block) + "\n")
    print("hosts: %d entries (%d fresh, %d kept from previous block) for %d names"
          % (len(lines), fresh, kept, len(wanted)))
    return 0


def clear():
    text = open(HOSTS, encoding="utf-8", errors="replace").read()
    open(HOSTS, "w", encoding="utf-8", newline="\n").write(strip(text))
    print("hosts: block removed")


def status():
    pinned = existing()
    print("hosts:        %s" % HOSTS)
    print("names wanted: %d" % len(set(NAMES)))
    print("names pinned: %d" % len(pinned))
    missing = [n for n in dict.fromkeys(NAMES) if n not in pinned]
    if missing:
        print("not pinned:   %s" % ", ".join(missing[:10]))
    for name in list(dict.fromkeys(NAMES))[:5]:
        if name in pinned:
            print("  %-24s %s" % (name, ", ".join(pinned[name])))


if __name__ == "__main__":
    {"apply": apply, "clear": clear, "status": status}.get(
        sys.argv[1] if len(sys.argv) > 1 else "apply", apply)()

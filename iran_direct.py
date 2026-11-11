#!/usr/bin/env python3
"""Keep Iranian traffic off the VPN tunnel -- works with Happ, Windscribe, anything.

    python iran_direct.py apply     # routes + DNS for Iranian sites (needs admin)
    python iran_direct.py clear     # undo
    python iran_direct.py status    # what is in force right now

Two independent layers:
  * routes: every geoip:ir block goes out the physical adapter, not the TUN.
    Longest-prefix match means a /24 beats the tunnel's 0.0.0.0/1, so this works
    under any VPN that does not run a strict-route firewall.
  * NRPT: Iranian domains resolve through Iranian DNS, never the VPN's.
"""
import argparse, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CIDR_FILE = os.path.join(HERE, "iran_cidrs.txt")
IR_DNS = ["217.218.155.155", "185.51.200.2"]
NS = [".ir", "digikala.com", "torob.com", "aparat.com", "sheypoor.com",
      "varzesh3.com", "cafebazaar.ir", "bmi.ir", "shaparak.ir"]
VIRTUAL = re.compile(r"TUN|TAP|WireGuard|Tailscale|Wintun|VPN|PPP|OpenVPN|Loopback|Hyper-V|Virtual", re.I)


def ps(script):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def cidrs():
    with open(CIDR_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def gateway():
    """(ifIndex, nextHop, description) of the physical adapter carrying the default route."""
    out = ps("Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | ForEach-Object {"
             " $a = Get-NetAdapter -InterfaceIndex $_.ifIndex -ErrorAction SilentlyContinue;"
             " \"$($_.ifIndex)|$($_.NextHop)|$($_.RouteMetric)|$($a.InterfaceDescription)\" }")
    best = None
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 4:
            continue
        idx, nh, metric, desc = parts
        if not nh or nh == "0.0.0.0" or VIRTUAL.search(desc):
            continue
        if best is None or int(metric or 0) < best[0]:
            best = (int(metric or 0), int(idx), nh, desc)
    return best[1:] if best else None


def routes():
    """{prefix: (nextHop, ifIndex)} for every non-default IPv4 route."""
    out = ps("Get-NetRoute -AddressFamily IPv4 | Where-Object {$_.DestinationPrefix -ne '0.0.0.0/0'} |"
             " ForEach-Object { \"$($_.DestinationPrefix)|$($_.NextHop)|$($_.ifIndex)\" }")
    table = {}
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            table[parts[0]] = (parts[1], parts[2])
    return table


def netsh(lines):
    """Run a batch of netsh route commands. Returns error output."""
    if not lines:
        return ""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    try:
        r = subprocess.run(["netsh", "-f", path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (r.stdout + r.stderr).strip()
    finally:
        os.unlink(path)


def apply():
    gw = gateway()
    if not gw:
        sys.exit("No physical adapter with a default route -- are you offline?")
    gw_idx, gw_hop, gw_desc = gw
    want = cidrs()
    have = routes()
    stale = [p for p in want if p in have and have[p][0] != gw_hop]
    missing = [p for p in want if p not in have or have[p][0] != gw_hop]
    deletes = ["interface ipv4 delete route %s interface=%s nexthop=%s" % (p, have[p][1], have[p][0])
               for p in stale]
    adds = ["interface ipv4 add route %s interface=%d nexthop=%s store=active" % (p, gw_idx, gw_hop)
            for p in missing]
    netsh(deletes)
    err = netsh(adds)
    print("gateway  %s via %s (if %d)" % (gw_hop, gw_desc, gw_idx))
    print("routes   %d added, %d stale removed, %d already correct" %
          (len(missing), len(stale), len(want) - len(missing)))
    if err:
        print("netsh:   " + err[:500])
    return len(missing)


def clear():
    have = routes()
    want = set(cidrs())
    drop = [p for p in want if p in have]
    netsh(["interface ipv4 delete route %s interface=%s nexthop=%s" % (p, have[p][1], have[p][0])
           for p in drop])
    print("routes   %d removed" % len(drop))


def nrpt_clear(quiet=False):
    ps("Get-DnsClientNrptRule | Where-Object { $_.Namespace[0] -in '%s' } | "
       "Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue" % "','".join(NS))
    if not quiet:
        print("dns      NRPT rules removed")


def nrpt_apply():
    nrpt_clear(quiet=True)  # re-adding the same namespace duplicates it
    for ns in NS:
        ps("Add-DnsClientNrptRule -Namespace '%s' -NameServers '%s' -ErrorAction SilentlyContinue"
           % (ns, "','".join(IR_DNS)))
    print("dns      NRPT -> %s for %s" % (", ".join(IR_DNS), " ".join(NS)))


def status():
    gw = gateway()
    print("gateway  " + ("%s via %s (if %d)" % (gw[1], gw[2], gw[0]) if gw else "none"))
    have, want = routes(), set(cidrs())
    mine = [p for p in want if p in have]
    right = [p for p in mine if gw and have[p][0] == gw[1]]
    print("routes   %d/%d Iranian blocks installed, %d pointing at the right gateway"
          % (len(mine), len(want), len(right)))
    rules = ps("Get-DnsClientNrptRule | ForEach-Object { $_.Namespace[0] }").split()
    print("dns      NRPT namespaces: %s" % (", ".join(rules) if rules else "none"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["apply", "clear", "status"])
    ap.add_argument("--no-dns", action="store_true", help="skip the NRPT layer")
    a = ap.parse_args()
    if a.action == "apply":
        apply()
        if not a.no_dns:
            nrpt_apply()
    elif a.action == "clear":
        clear()
        nrpt_clear()
    else:
        status()


if __name__ == "__main__":
    main()

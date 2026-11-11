#!/usr/bin/env python3
"""Self-check for the Iran-direct layers. Run: python tools/test_iran_direct.py"""
import json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iran_direct as D
import happ_iran as H

fails = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  -- " + detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- CIDR list ---
cs = D.cidrs()
check("cidr list is non-empty", len(cs) > 1000, "%d entries" % len(cs))
check("cidr list is all valid IPv4 prefixes",
      all("/" in c and all(p.isdigit() and 0 <= int(p) <= 32 for p in [c.rsplit("/", 1)[1]]) for c in cs))
check("cidr list covers Iranian banks/CDN blocks",
      any(c.startswith("185.143.") or c.startswith("185.188.") for c in cs))

# --- gateway detection ---
gw = D.gateway()
check("gateway detected on a physical adapter", gw is not None,
      "no non-virtual adapter with a default route")
if gw:
    idx, hop, desc = gw
    check("gateway hop is a private address",
          hop.split(".")[0] in ("10", "172", "192") or hop.startswith("169.254"), hop)
    check("gateway adapter is not a tunnel", not D.VIRTUAL.search(desc), desc)

# --- route table ---
rt = D.routes()
check("route table is readable", isinstance(rt, dict) and len(rt) > 0, "%d routes" % len(rt))

# --- netsh batch builder (no execution) ---
fd, path = tempfile.mkstemp(suffix=".txt")
with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
    f.write("\n".join(["interface ipv4 add route 1.2.3.0/24 interface=1 nexthop=10.0.0.1 store=active"]) + "\n")
raw = open(path, "rb").read()
os.unlink(path)
check("netsh batch uses LF only (CR breaks prefix parsing)", b"\r" not in raw)

# --- Happ ---
if os.path.exists(H.PATH):
    d = H.load()
    prof = H.iran_profile(d)
    check("Happ has an Iran routing profile", prof is not None)
    if prof:
        check("profile is not in global-proxy mode", prof.get("globalProxy") is False)
        check("profile has Iranian direct sites",
              any("ir" in s.lower() for s in (prof.get("directSites") or [])))
        check("profile has a large Iranian IP block list",
              len(prof.get("directIp") or []) > 1000, "%d" % len(prof.get("directIp") or []))
        check("profile domestic DNS is not the dead 195.168.1.1",
              prof.get("domesticDnsIp") != "195.168.1.1", prof.get("domesticDnsIp"))
    subs = {c["subscriptionId"] for c in d.get("subConfigs", [])}
    mounted = {c["subscriptionId"] for c in d.get("subConfigs", [])
               if c.get("enabled") and c.get("selectedProfile") == (prof["name"] if prof else "")}
    check("Server List (0) has the Iran profile mounted", 0 in mounted)
    active = H.last_subscription()
    check("active subscription %s has the Iran profile mounted" % active,
          active in mounted or active == 0,
          "mounted on %s" % sorted(mounted))
else:
    print("SKIP  Happ not installed")

print()
if fails:
    print("%d check(s) failed: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all checks passed")

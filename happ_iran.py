#!/usr/bin/env python3
"""Keep Happ's Iran routing profile mounted on whichever subscription is active.

    python happ_iran.py apply    # mount the Iran profile on the active subscription
    python happ_iran.py status   # show what is mounted where

Happ stores routing profiles in %LOCALAPPDATA%\\Happ\\routing.json. Each profile
belongs to one subscription (subscriptionId 0 = "Server List"). A profile mounted
on the Server List is invisible to a real subscription, and Happ then silently
disables routing for it ("Connection latch: routing disabled for sub N") -- so all
traffic goes through the tunnel and Iranian sites break.

Run this while Happ is closed: Happ rewrites routing.json on exit.
"""
import json, os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _user_localappdata():
    """LOCALAPPDATA of the logged-in user; the scheduled task runs as SYSTEM."""
    if "LOCALAPPDATA" in os.environ and os.path.isdir(os.environ["LOCALAPPDATA"]):
        p = os.path.join(os.environ["LOCALAPPDATA"], "Happ", "routing.json")
        if os.path.exists(p):
            return os.path.dirname(os.path.dirname(p))
    root = os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "Users")
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "AppData", "Local", "Happ", "routing.json")
        if os.path.exists(p):
            return os.path.join(root, name, "AppData", "Local")
    raise SystemExit("Happ routing.json not found")


PATH = os.path.join(_user_localappdata(), "Happ", "routing.json")
IR_DNS = "217.218.155.155"
WANT = ("ir", "avalai")


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(d):
    shutil.copy2(PATH, PATH + ".bak")
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def _happ_key():
    """HKCU\\Software\\Happ, or the user's hive when running as SYSTEM."""
    import winreg
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_USERS):
        try:
            if root is winreg.HKEY_CURRENT_USER:
                return winreg.OpenKey(root, r"Software\Happ")
            for i in range(winreg.QueryInfoKey(root)[0]):
                sid = winreg.EnumKey(root, i)
                if sid.endswith("_Classes"):
                    continue
                try:
                    return winreg.OpenKey(root, sid + r"\Software\Happ")
                except OSError:
                    continue
        except OSError:
            continue
    return None


def last_subscription():
    import winreg
    try:
        k = _happ_key()
        if k is None:
            return 0
        with winreg.OpenKey(k, r"OrganizationDefaults\Preferences") as p:
            return int(winreg.QueryValueEx(p, "lastSubscription")[0])
    except (OSError, ValueError):
        return 0


def happ_running():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "if (Get-Process Happ -ErrorAction SilentlyContinue) { 'yes' }"],
                       capture_output=True, text=True)
    return "yes" in r.stdout


def iran_profile(d):
    """The profile carrying Iranian direct rules, preferring the richest one."""
    best = None
    for p in d.get("routings", []):
        sites = " ".join(p.get("directSites") or []).lower()
        if any(w in sites for w in WANT):
            score = len(p.get("directIp") or [])
            if best is None or score > best[0]:
                best = (score, p)
    return best[1] if best else None


def apply():
    d = load()
    sub = last_subscription()
    prof = iran_profile(d)
    if not prof:
        sys.exit("No Iran routing profile found in routing.json.")

    name = prof["name"]
    prof["globalProxy"] = False
    if prof.get("domesticDnsIp") in (None, "", "195.168.1.1"):
        prof["domesticDnsIp"] = IR_DNS
        prof["domesticDnsType"] = "DoU"

    # mount on the active subscription (and the Server List, which always applies)
    cfg = {c["subscriptionId"]: c for c in d.get("subConfigs", [])}
    for sid in {0, sub}:
        c = cfg.get(sid)
        if c is None:
            c = {"subscriptionId": sid, "enabled": True, "ignoreProfile": False,
                 "selectedProfile": name, "providerRoutingDisabled": False}
            d["subConfigs"].append(c)
        else:
            c["enabled"] = True
            c["ignoreProfile"] = False
            c["selectedProfile"] = name
            c["providerRoutingDisabled"] = False

    d["activeRoutingName"] = name
    save(d)
    print("mounted  %r on subscriptions %s" % (name, sorted({0, sub})))
    print("dns      domestic %s (%s)" % (prof["domesticDnsIp"], prof["domesticDnsType"]))


def status():
    d = load()
    sub = last_subscription()
    prof = iran_profile(d)
    print("active subscription: %s" % sub)
    print("iran profile:        %s" % (prof["name"] if prof else "MISSING"))
    for c in d.get("subConfigs", []):
        mark = "<-- active" if c["subscriptionId"] == sub else ""
        print("  sub %-12s enabled=%-5s profile=%r %s"
              % (c["subscriptionId"], c["enabled"], c["selectedProfile"], mark))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if happ_running():
        # Happ rewrites routing.json on exit; patching now would be undone.
        print("Happ is running -- skipping (routing.json is rewritten on exit)")
        sys.exit(0)
    {"apply": apply, "status": status}.get(action, lambda: sys.exit(__doc__))()


if __name__ == "__main__":
    main()

# Prompt: make Iranian sites work while a VPN is on

Paste everything below the line into Claude Code (or any other coding agent) on the
target Windows machine. The agent will diagnose, fix, verify, and automate it.

---

I'm in Iran using a VPN — Happ, or possibly Windscribe/v2rayN. With the tunnel on,
Iranian sites (banks, `sso.my.gov.ir`, `api.avalai.ir`, varzesh3, Digikala) fail while
foreign sites work. I need both at once, permanently, across Wi-Fi changes and reboots.

There is a repo checked out here with `iran_hosts.py`, `iran_direct.py`,
`happ_iran.py`, `happ_excluded.py`, `iran_cidrs.txt`, and a README that explains the
design. **Read the README first.**

## Do not skip the diagnosis

Before changing anything, prove the failure on *this* machine. With the tunnel up:

1. `Find-NetRoute -RemoteIPAddress <iranian-ip>` vs `<foreign-ip>` — expect `Wi-Fi` vs
   the tunnel adapter. If Iranian traffic is *not* already routed direct, the problem is
   different from the one this repo solves; stop and report.
2. `curl --resolve www.varzesh3.com:443:<its-ip> https://www.varzesh3.com` — if this
   returns 200/301 while `curl https://www.varzesh3.com` returns 000, the fault is DNS.
3. `Resolve-DnsName www.varzesh3.com` — expect no answer.
4. A raw UDP/53 query to `217.218.155.155` from Python — expect a correct answer.

If step 4 also fails, this fix will not work on this machine — say so instead of
applying it blindly.

## The fix

```powershell
Set-ItemProperty 'C:\Windows\System32\drivers\etc\hosts' -Name IsReadOnly -Value $false
python iran_hosts.py apply
```

Add the sites the user actually visits to `NAMES` in `iran_hosts.py` first.

Then, with Happ **closed**, mount the Iran routing profile on the active subscription:

```
python happ_iran.py apply
```

## Verify properly — this is where it goes wrong

Turning the tunnel on can drop **your own** connection (the user's agent may be talking
to an Iranian endpoint). So:

- Run the verification **detached**, writing results to a log file, and read the log
  afterwards. Never rely on output that has to survive in the live session.
- A `curl`-only pass is not proof. Check `api.ipify.org` **with the tunnel up**: if it
  still shows the normal ISP address, the tunnel is not actually up and every other
  result is meaningless.
- Only report success when all of these hold **simultaneously**:

```
api.ipify.org     -> VPN IP (not the ISP IP)
varzesh3.com      -> 301/200
api.avalai.ir     -> 200
sso.my.gov.ir     -> 302
digikala.com      -> 200
google.com        -> 200
github.com        -> 200
```

Then leave it running for a few minutes and sample repeatedly — the earlier version of
this fix passed once and broke minutes later, because the scheduled task rewrote the
hosts block empty when resolution failed. Confirm `iran_hosts.py apply` run **while the
tunnel is up** reports `kept from previous block` and does not empty the block.

## Make it stick

Register a scheduled task that runs `iran_hosts.py apply` at logon and on network change
(`Microsoft-Windows-NetworkProfile` event 10000), as SYSTEM, and confirm
`LastTaskResult` is 0.

## Traps already found — don't rediscover them

- `excludedRoutes` is **not implemented for Xray TUN** (only sing-box). The JSON-array
  and comma-space formats make Happ **fail to connect entirely**; newline format
  connects but does nothing. `tunProvider=singbox` is ignored — Happ still builds
  `happ-xray`.
- Kernel routes and NRPT are both defeated by Happ's strict-route WFP firewall while the
  tunnel is up. They only help when it is off.
- `1.1.1.1` and `8.8.8.8` return **NXDOMAIN** for `varzesh3.com`.
- `C:\Windows\System32\drivers\etc\hosts` ships **read-only**.
- `happ://connect`, `happ://disconnect`, `happ://toggle` are real deeplinks.
- `195.168.1.1` (the stock Chocolate4U domestic DNS) is dead. Use `217.218.155.155`.
- A routing profile mounted on `subscriptionId 0` ("Server List") is invisible to a real
  subscription; Happ then logs `Connection latch: routing disabled for sub N`.

## Report honestly

State which layer you verified and how. If something did not work, say so with the
observation. Do not claim success from `route print` alone, and do not claim a browser
test you did not run.

## If the user switches VPN

The hosts layer is VPN-agnostic and keeps working. Routing then belongs to that VPN: use
its split-tunnel list, or `iran_direct.py` if it has no strict-route firewall. Re-verify
with the same detached probe.

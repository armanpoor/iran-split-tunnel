# Prompt: make Iranian sites work while a VPN is on

Paste everything below the line into Claude Code (or any coding agent) on the target
Windows machine.

---

I'm in Iran using a VPN — Happ, or possibly Windscribe/v2rayN. With the tunnel on,
Iranian sites fail while foreign sites work. I need both at once, across Wi-Fi changes
and reboots.

This repo is checked out here: `iran_hosts.py`, `happ_dns.py`, `happ_iran.py`,
`iran_direct.py`, `happ_excluded.py`, `iran_cidrs.txt`, and a README that records what
was measured. **Read the README first** — most of what follows was learned the hard way.

## Diagnose before changing anything

With the tunnel up, establish which layer is actually broken:

1. `Find-NetRoute -RemoteIPAddress <iranian-ip>` vs `<foreign-ip>` — expect `Wi-Fi` vs
   the tunnel adapter. **Routing is usually already correct.** If it isn't, stop: this
   is a different problem.
2. `curl --resolve www.varzesh3.com:443:<its-ip> https://www.varzesh3.com` vs
   `curl https://www.varzesh3.com`. If the first works and the second returns 000, the
   fault is **DNS**.
3. `Resolve-DnsName www.varzesh3.com` — expect no answer while the tunnel is up.

4. **Take a tunnel-OFF baseline of every site you test.** This matters: banks
   (`bankmellat`, `refah-bank`, `banksepah`, `saderat-bank`), `snapp`, `tasnimnews`,
   `farsnews`, `sampad` and `bmi` were measured returning 000 with the tunnel **off**
   too — they are blocked by the ISP, and no local change fixes them. Counting them as
   failures will make a working setup look broken.

## Apply the fix

```powershell
Set-ItemProperty 'C:\Windows\System32\drivers\etc\hosts' -Name IsReadOnly -Value $false
python iran_hosts.py apply        # the reliable layer
python happ_dns.py apply          # Happ must be closed
```

Add the sites the user actually visits to `NAMES` in `iran_hosts.py`. **Do not try to
pin the whole `.ir` zone**: 5,000 hosts entries made every lookup take 5.6 s on Windows
11 and 20,000 made it unusable. The script refuses above 2,000 — keep it in the
hundreds.

## Verify honestly

Turning the tunnel on can drop **your own** connection, so run verification **detached**
and read the log afterwards.

- `api.ipify.org` with the tunnel up must show the **VPN** IP. If it still shows the
  ISP address, the tunnel is not actually up and every other result is meaningless.
- Sample **several rounds**, not one. `happ_dns.py` alone measured 30/41 on one run and
  15/47 on another — it is not deterministic. The hosts layer was stable at 14/14
  across three consecutive rounds.
- Report regressions separately from ISP blocks, using the tunnel-off baseline.

## Traps already hit — don't rediscover them

- `excludedRoutes` is **not implemented for Xray TUN** (sing-box only). JSON-array and
  comma-space formats make Happ **fail to connect entirely**; newline connects but does
  nothing. `tunProvider=singbox` is ignored.
- Setting Happ's `remoteDnsIp` to an Iranian address makes Happ route the resolver into
  the tunnel — Iranian sites then drop to 6/41.
- Kernel routes and NRPT are defeated by Happ's strict-route WFP firewall while the
  tunnel is up; they only help when it is off.
- A local DNS proxy on `127.0.0.1:53` is dropped by Happ's filters.
- `1.1.1.1` and `8.8.8.8` return **NXDOMAIN** for `varzesh3.com`.
- `C:\Windows\System32\drivers\etc\hosts` ships **read-only**.
- `happ://connect`, `happ://disconnect`, `happ://toggle` are real deeplinks.
- `195.168.1.1` (stock Chocolate4U domestic DNS) is dead. Use `217.218.155.155`.
- A routing profile mounted on `subscriptionId 0` ("Server List") is invisible to a real
  subscription; Happ then logs `Connection latch: routing disabled for sub N`.

## Automate

Register a scheduled task running `iran_hosts.py apply` at logon and on network change
(`Microsoft-Windows-NetworkProfile` event 10000), as SYSTEM, and confirm
`LastTaskResult` is 0.

## If the user switches VPN

The hosts layer is VPN-agnostic and keeps working. Routing then belongs to that VPN: use
its split-tunnel list, or `iran_direct.py` if it has no strict-route firewall.

## Report

State which layer you verified and how many rounds. Say plainly if something did not
work. Do not claim success from `route print` alone, and do not claim a browser test you
did not run.

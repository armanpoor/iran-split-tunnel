# iran-split-tunnel

**Keep Iranian websites working while your VPN is on.**

If you live in Iran and use a VPN, you know this trade-off: turn the VPN on to reach
Claude, Gemini, GitHub and ChatGPT — and every Iranian site dies. Banks, `sso.my.gov.ir`,
Shaparak, Digikala, and Iranian AI endpoints like `api.avalai.ir` either time out or
return `403 Forbidden` because the request now arrives from a foreign datacenter.

This repo makes both work at the same time: **foreign traffic through the tunnel,
Iranian traffic direct** — and it keeps working when you switch Wi-Fi, reboot, or
change VPN provider.

Tested on Windows 11 with **Happ 4.7.2** (Xray TUN). The core fix is VPN-agnostic.

---

## Why this is harder than it looks

You'd think `route add` for Iranian IP ranges solves it. It doesn't, and the reason is
worth knowing before you try.

Modern VPN clients (Happ included) install a **strict-route firewall** — on Happ, 21
WFP filters. That firewall outranks the Windows route table. You can have 2095/2095
Iranian routes installed and perfectly correct, and Iranian sites still fail, because
the packets never consult the table.

Then there's DNS, which is a second, independent trap:

- Cloudflare (`1.1.1.1`) and Google (`8.8.8.8`) return **NXDOMAIN** for `varzesh3.com`.
  So a VPN that resolves names through foreign DoH breaks Iranian domains even when
  routing is right.
- While Happ's tunnel is up, Windows' own resolver returns **nothing** for Iranian
  names — but a **raw UDP/53 query** to `217.218.155.155` still answers correctly.
  The WFP filters catch the resolver, not raw sockets.

That last observation is the whole trick behind this repo.

---

## What actually works

`iran_hosts.py` resolves Iranian domains itself over raw UDP/53 — bypassing the
intercepted resolver — and writes the answers into the hosts file. Windows then never
needs to look them up.

Measured with the tunnel genuinely up (`api.ipify.org` showing the VPN IP):

| Site | Status | Site | Status |
|---|---|---|---|
| `varzesh3.com` | 301 | `api.avalai.ir` | 200 |
| `sso.my.gov.ir` | 302 | `digikala.com` | 200 |
| `divar.ir` | 200 | `aparat.com` | 200 |
| `google.com` | 200 | `github.com` | 200 |

Routing confirmed by `Find-NetRoute`:

```
185.143.233.133  -> Wi-Fi       (Iranian, direct)
78.38.239.18     -> Wi-Fi       (Iranian, direct)
142.250.185.78   -> happ-xray   (foreign, through the tunnel)
```

---

## What does *not* work (all tested)

| Approach | Why it fails |
|---|---|
| **Kernel routes** (`route add` / `netsh`) | Happ's strict-route firewall outranks the Windows route table. |
| **NRPT rules** | Intercepted before they apply. 19 rules active, still no DNS answer. |
| **DNS on the TUN adapter** | Happ rewrites it at connect time. |
| **Happ `excludedRoutes`** | Only implemented for the **sing-box** TUN. On **Xray TUN** it is silently ignored. Worse: the JSON-array and comma-space formats make Happ **fail to connect entirely**. |
| **Foreign DoH only** | NXDOMAIN for `varzesh3.com`. |

---

## Quick start

Requires Python 3.8+ and an Administrator terminal.

```powershell
# 1. hosts ships read-only on Windows
Set-ItemProperty 'C:\Windows\System32\drivers\etc\hosts' -Name IsReadOnly -Value $false

# 2. pin Iranian domains to their real IPs
python iran_hosts.py apply

# 3. check it
python iran_hosts.py status
```

That's it. Turn your VPN on and browse.

To undo:

```powershell
python iran_hosts.py clear
```

### Adding sites

Edit the `NAMES` list at the top of `iran_hosts.py` and re-run `apply`. Any domain that
resolves through an Iranian resolver belongs there.

---

## Using this on another machine (any harness)

`PROMPT.md` is a self-contained prompt. Copy it into Claude Code, Cursor, Codex, or any
other agent on the new machine and it will diagnose the machine, apply the fix, verify
it with the tunnel actually up, and register a scheduled task. It carries every trap
listed above so the agent doesn't rediscover them.

```
You: <paste PROMPT.md>
```

---

## Files

| File | Purpose |
|---|---|
| `iran_hosts.py` | **the fix** — resolves Iranian names over raw UDP/53 and pins them in hosts |
| `iran_direct.py` | kernel routes + NRPT — useful when the tunnel is **off**, no effect while it's on |
| `happ_iran.py` | mounts the Iran routing profile on whichever Happ subscription is active |
| `happ_excluded.py` | writes Happ's `excludedRoutes` (only meaningful on sing-box TUN) |
| `iran_cidrs.txt` | 2095 Iranian IPv4 blocks from Chocolate4U `geoip.dat` |
| `test_iran_direct.py` | 15 assertions, no network required |
| `PROMPT.md` | the prompt for another machine |

---

## Why the script keeps a stale entry instead of deleting it

Early versions rewrote the hosts block from scratch on every run. When the tunnel was
up and resolution failed, the block was rewritten **empty** — so access broke a few
minutes after it had been working, which looked like the fix "randomly stopped".

`apply` now keeps any entry it cannot re-resolve, and refuses to write an empty block.
Resolution is also parallel with a short deadline, so the scheduled task returns in
about a second instead of hanging.

---

## Keeping it fresh

Iranian CDN addresses rotate. A scheduled task that runs `iran_hosts.py apply` at logon
and on network change keeps the pins current; `PROMPT.md` sets one up. If a site starts
failing, re-run `apply`.

---

## Limits

- **IPv4 only.** The tunnel is IPv4-only and Iranian v6 ranges are few.
- **Hosts pinning doesn't follow CDN rotation** between runs — re-run `apply` if a site
  goes stale.
- **`happ_iran.py` needs Happ closed**; Happ rewrites `routing.json` on exit.
- **Other VPNs:** the hosts layer works with any VPN. Routing is then that VPN's job —
  use its split-tunnel list, or fall back to `iran_direct.py` if it has no strict-route
  firewall.
- Windows only. The DNS trick is Windows/WFP specific.

## License

MIT — see `LICENSE`.

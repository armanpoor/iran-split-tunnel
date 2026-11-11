# iran-split-tunnel

**Keep Iranian websites working while your VPN is on.**

Turn the VPN on to reach Claude, Gemini, GitHub and ChatGPT, and every Iranian site
dies — banks, `sso.my.gov.ir`, Shaparak, Digikala, `api.avalai.ir` — because the
request now arrives from a foreign datacenter.

This repo keeps both working at once: **foreign traffic through the tunnel, Iranian
traffic direct.** Tested on Windows 11 with Happ 4.7.2 (Xray TUN).

---

## Why this is harder than it looks

You'd think adding routes for Iranian IP ranges solves it. It doesn't.

Modern VPN clients install a **strict-route firewall** — Happ creates 21 WFP filters.
That firewall outranks the Windows route table, so you can have every Iranian route
installed and correct and Iranian sites still fail.

DNS is a second, independent trap:

- Cloudflare (`1.1.1.1`) and Google (`8.8.8.8`) return **NXDOMAIN** for `varzesh3.com`.
  Measured. An Iranian resolver (`217.218.155.155`) returns real A records.
- While Happ's tunnel is up, Windows' resolver returns **nothing** for Iranian names,
  `ping` says "could not find host", and the browser times out — even though the
  traffic itself is already being routed direct.

So the failure is almost never routing. It is name resolution.

---

## What works

Two layers. Both are needed.

### 1. Pin the sites you actually use (`iran_hosts.py`)

A hosts entry sidesteps DNS entirely: the name is already an address, so there is
nothing left to look up. This survives any VPN, any firewall, any DNS hijack.

```powershell
Set-ItemProperty 'C:\Windows\System32\drivers\etc\hosts' -Name IsReadOnly -Value $false
python iran_hosts.py apply
```

Measured with the tunnel genuinely up (`api.ipify.org` = VPN IP), three consecutive
rounds, 14 sites including `varzesh3`, `avalai`, `sso.my.gov.ir`, `digikala`, `irna`,
`cafebazaar`, `aparat`, `divar`, `shaparak`, `google`, `github`:

```
round 1 : 14/14
round 2 : 14/14
round 3 : 14/14
```

**Keep the list small.** Windows scans the hosts file linearly — measured on Windows
11: 5,000 entries made every lookup take **5.6 s**, 20,000 timed out entirely. A few
hundred is fine; the whole `.ir` zone is not. `iran_hosts.py` refuses above 2,000.

### 2. Fix Happ's DNS (`happ_dns.py`)

For sites not pinned, Happ must resolve Iranian names itself. The stock profile can't:
its domestic resolver (`195.168.1.1`) is dead, and its remote DoH (Cloudflare) answers
NXDOMAIN for Iranian domains.

```powershell
python happ_dns.py apply      # Happ must be closed
```

It sets domestic DNS to `217.218.155.155` (answers `.ir` *and* foreign) while leaving
the remote path on Cloudflare. Measured across a 41-site survey:

| domestic | remote | fakeDns | Iranian sites OK |
|---|---|---|---|
| `195.168.1.1` (stock, dead) | 1.1.1.1/DoH | true | 5/41 |
| `217.218.155.155` | 1.1.1.1/DoH | false | **30/41** |
| `217.218.155.155` | `217.218.155.155` | false | 6/41 |

The third row is a trap: if the resolver itself is Iranian, Happ routes the resolver
*into the tunnel* and everything collapses.

---

## What does *not* work (each measured)

| Approach | Why it fails |
|---|---|
| Kernel routes (`route add` / `netsh`) | Happ's strict-route firewall outranks the Windows route table. 2095/2095 routes correct, sites still failed. |
| NRPT rules | Intercepted before they apply. 19 rules active, still no DNS answer. |
| DNS on the TUN adapter | Happ rewrites it at connect time. |
| Local DNS proxy on 127.0.0.1:53 | Happ's WFP filters drop the queries. |
| Happ `excludedRoutes` | Only implemented for the **sing-box** TUN; this machine runs **Xray TUN**. Also: JSON-array and comma-space formats make Happ **fail to connect entirely**. |
| Pinning the whole `.ir` zone in hosts | 5k entries → 5.6 s per lookup; 20k → unusable. |

---

## Honest limits

- **`happ_dns.py` is not fully deterministic.** The same configuration measured 30/41
  once and 15/47 on another run. That is why the hosts layer exists — it is the
  reliable one. Treat `happ_dns.py` as an improvement, not a guarantee.
- **Some Iranian sites are blocked by the ISP**, not the VPN. Measured with the tunnel
  **off**: `bankmellat`, `refah-bank`, `banksepah`, `saderat-bank`, `snapp`,
  `tasnimnews`, `farsnews`, `sampad`, `bmi` all return 000 either way. No tooling fixes
  those; they need a different network path.
- **IPv4 only.**
- **`happ_*.py` need Happ closed** — it rewrites `routing.json` on exit.
- **Windows only.**

---

## Using this on another machine

`PROMPT.md` is a self-contained prompt. Paste it into Claude Code, Cursor, Codex or any
other agent on the target machine. It carries every measurement and trap above so the
agent does not rediscover them.

---

## Files

| File | Purpose |
|---|---|
| `iran_hosts.py` | **the reliable fix** — pins the sites you list, bypassing DNS |
| `happ_dns.py` | fixes Happ's domestic resolver (improvement, not a guarantee) |
| `happ_iran.py` | mounts the Iran routing profile on the active Happ subscription |
| `iran_direct.py` | kernel routes + NRPT — useful only when the tunnel is **off** |
| `happ_excluded.py` | writes Happ's `excludedRoutes` (sing-box TUN only) |
| `iran_cidrs.txt` | 2095 Iranian IPv4 blocks from Chocolate4U `geoip.dat` |
| `test_iran_direct.py` | 15 assertions, no network needed |
| `PROMPT.md` | the prompt for another machine |

## Automatic

A scheduled task (`IranDirectRoutes`) runs `iran_hosts.py apply` and
`iran_direct.py apply` at boot, at logon, and on every network change, as SYSTEM.

## License

MIT — see `LICENSE`.

# Driving Claude Code from a phone or tablet

How to continue a coding session from a phone/tablet — and, crucially, **which
paths keep this repo's hook-based enforcement live**. Verified against vendor docs
2026-06-22; version numbers move fast, so re-check before relying on a minimum.

## TL;DR

| You want… | Use | Enforcement (hooks/DAG guard) |
|---|---|---|
| Steer an in-progress session from your phone, full local env | **Remote Control** | ✅ runs on your machine |
| Kick off a task with no local machine on | Claude Code on the web / cloud session | ❌ cloud sandbox — hooks don't run |
| Fully headless box, or a non-Claude tool | **tmux + Tailscale** | ✅ (it's your local shell) |

The decisive fact: **enforcement is tied to *where the session executes*, not which
device you hold.** The scaffolded hooks (`github_command_guard.sh`, the DAG guard,
`prod_guard.py`) only run where a real shell runs — your machine. See the
local-vs-cloud boundary in [`non-cli-surface-matrix.md`](non-cli-surface-matrix.md)
and the generated `CAPABILITIES.md` (ADR-007: git/CI is the boundary cloud surfaces
still honor).

## Option A — Remote Control (recommended for Claude Code)

Claude Code's built-in way to drive a **local** session from the Claude mobile app
or any browser. Because the session runs on your machine, your filesystem, MCP
servers, tools, and **all the scaffolded hooks stay active** — even when you're
typing from your phone.

- **Enable:** `claude remote-control` (server mode, prints a URL + QR), or
  `claude --remote-control` / `--rc` for a normal interactive session that's also
  remote-drivable, or `/remote-control` (`/rc`) from a live session. VS Code: `/rc`.
- **Requires:** Claude Code (the floor was v2.1.51; mobile push needs v2.1.110+ —
  check `claude --version`), a claude.ai `/login` (not an API key / `setup-token`).
  All plans (on Team/Enterprise an admin enables it).
- **Networking:** outbound HTTPS only — it never opens an inbound port, so it
  **sidesteps the WSL2 NAT problem entirely** (no Tailscale/SSH/port-forward needed).
- **Caveats:** the local `claude` process must stay alive (close the terminal →
  session ends); a >~10-minute total network outage on your machine times it out;
  a few interactive commands (`/plugin`, `/resume`) stay local-only; starting an
  ultraplan session disconnects Remote Control.

Related phone triggers (also local-execution, so hooks run): **Dispatch** (message a
task from the app → spawns a Desktop session) and **Channels** (Telegram/Discord →
local session).

## Option B — tmux + Tailscale (headless, or non-Claude tools)

For keeping a machine working after you fully disconnect, or driving tools other
than Claude Code. This environment is **Windows 11 + WSL2**, whose NAT means the
WSL VM isn't reachable at the host IP without help.

1. **tmux** (survives disconnects): `tmux new -s work` → run your tool →
   `Ctrl-b d` to detach → `tmux attach -t work` to resume. A dropped phone
   connection never kills the session.
2. **Transport — Tailscale (cleanest):** install Tailscale **on the Windows host**
   (not inside WSL — `tailscaled` in WSL2 fights the TUN device), and on the phone,
   same account. Run `sshd` inside WSL on an alt port; connect to the host's tailnet
   name. No port-forwarding, works over cellular.
   - Add **mosh** for flaky mobile links (local echo + roaming). mosh needs UDP, so
     it only works over Tailscale or WSL2 mirrored mode — **not** `netsh portproxy`.
   - iOS Tailscale grabs port 22; the clean fix is a Windows OpenSSH server on alt
     ports that `ForceCommand`s into `wsl.exe`.
3. **Alternatives:** WSL2 `networkingMode=mirrored` (LAN-only, no NAT); Cloudflare
   Tunnel / `sshx` / `tmate` (no open ports, browser terminal); `code tunnel` →
   `vscode.dev` (full editor + integrated terminal from a tablet).

**Mobile clients:** iOS — Blink Shell or Moshi (native mosh); Android — Termux
(`pkg install openssh mosh tmux`; use it as a *client* — running Claude Code natively
in Termux is unreliable on ARM). Termius/JuiceSSH work but lack mosh.

## Which to pick

- Driving **Claude Code** specifically, machine on → **Remote Control** (zero
  network plumbing, full enforcement).
- Machine must keep running **after you disconnect**, or a **non-Claude** tool →
  **tmux + Tailscale**.
- No local machine at all → **Claude Code on the web** — but accept that the
  scaffolded hooks don't run there; git + CI are your only guardrails.

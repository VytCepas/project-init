# Driving Claude Code from a phone or tablet

How to continue a coding session from a phone/tablet — and, crucially, **which
paths keep this repo's hook-based enforcement live**. Verified against vendor docs
2026-06-22; version numbers move fast, so re-check before relying on a minimum.

## TL;DR

| You want… | Use | Enforcement (hooks/DAG guard) |
|---|---|---|
| Steer an in-progress session from your phone, full local env | **Remote Control** | ✅ runs on your machine |
| Kick off a task with no local machine on | Claude Code on the web / cloud session | ⚠️ repo-committed hooks can run in-sandbox; no local config — git/CI is the boundary |
| Fully headless box, or a non-Claude tool | **tmux + Tailscale** | ✅ (it's your local shell) |

The decisive fact: **enforcement depends on *where the session executes*, not which
device you hold.** A session on your machine applies your full local config — the
scaffolded hooks (`github_command_guard.sh`, the DAG guard, `prod_guard.py`) plus
anything in `~/.claude`. A cloud sandbox honors only **repo-committed** files:
committed hooks may run inside the VM, but your local user config, resources, and
credentials don't — so per ADR-007 **git/CI is the guaranteed enforcement boundary**
for cloud surfaces. See the local-vs-cloud caveat in
[`non-cli-surface-matrix.md`](non-cli-surface-matrix.md) and the generated
`CAPABILITIES.md`.

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
   same account. The host is now reachable at its tailnet name — but **WSL's `sshd`
   sits behind WSL2's NAT**, so the tailnet connection lands on the *Windows host*,
   not WSL, unless you bridge it. Pick one:
   - **WSL2 mirrored networking** (`networkingMode=mirrored` in `.wslconfig`) so WSL
     shares the host's network stack and tailnet — simplest, and it passes UDP (so
     mosh works);
   - a Windows `netsh portproxy` from a host port → `<WSL-ip>:22` (TCP only — no mosh); or
   - a Windows OpenSSH server that `ForceCommand`s into `wsl.exe` (this also solves
     iOS Tailscale grabbing port 22).

   Then connect to `<host-tailnet-name>:<port>` — no inbound internet ports, works
   over cellular. Add **mosh** for flaky links (local echo + roaming); it needs UDP,
   so use mirrored mode (not portproxy).
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
- No local machine at all → **Claude Code on the web** — the sandbox honors only
  repo-committed config (not your local setup), so git + CI are your guaranteed
  guardrails there.

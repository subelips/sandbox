"""Generate the Kaggle sandbox notebook + kernel metadata."""
import json
import pathlib

BOOT = r'''
# ═══════════════════════════════════════════════════════════════════════════
#  KAGGLE SANDBOX - BOOT  (Hermes Agent + OpenSSH + Pinggy TCP)
#  Every step is timed. Nothing is skipped or trimmed: the full agent tree
#  comes out of the .pkg dataset exactly as the official installer built it.
# ═══════════════════════════════════════════════════════════════════════════
import json, os, pathlib, shutil, socket, subprocess, sys, time, urllib.parse, urllib.request

T0 = time.time()
def log(m): print(f"[{time.time()-T0:7.1f}s] {m}", flush=True)
def sh(c, timeout=600, check=False):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {c}\n{r.stdout}\n{r.stderr}")
    return r

IN = pathlib.Path("/kaggle/input")
def need(name):
    for p in IN.rglob(name):
        return p
    raise SystemExit(f"FATAL: {name} not mounted under /kaggle/input")

SEC   = json.loads(need("secrets.json").read_text())
PINGGY, TG, SSH, GH, LLM = SEC["pinggy"], SEC["telegram"], SEC["ssh"], SEC["github"], SEC.get("llm") or {}
HOME  = pathlib.Path("/root")
HH    = HOME / ".hermes"
LOGSD = HH / "logs"; LOGSD.mkdir(parents=True, exist_ok=True)
PUBLIC_STATE = f"https://raw.githubusercontent.com/{GH['repo']}/main/state.json"

def tg(text, silent=True):
    if not TG.get("bot_token"):
        return
    data = urllib.parse.urlencode({
        "chat_id": TG["chat_id"], "text": text[:4000], "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true" if silent else "false"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG['bot_token']}/sendMessage",
                               data=data, timeout=20).read()
    except Exception as e:
        log(f"telegram: {e}")

log("secrets.json loaded")
log(f"kernel run type: {os.environ.get('KAGGLE_KERNEL_RUN_TYPE')}")
'''

EXTRACT = r'''
# ── 1. full agent tree from the .pkg dataset (no reinstall, no network) ─────
pkg = need("hermes-agent-full.pkg")
log(f"pkg: {pkg}  {pkg.stat().st_size/1e6:.0f} MB")
t = time.time()
ext = sh(f'tar -C / --zstd -xf "{pkg}"', timeout=900)
if ext.returncode != 0:
    log("tar --zstd unavailable, falling back to zstd pipe")
    ext = sh(f'zstd -dc "{pkg}" | tar -C / -xf -', timeout=900)
if ext.returncode != 0:
    log("falling back to gzip")
    ext = sh(f'gzip -dc "{pkg}" | tar -C / -xf -', timeout=900)
if ext.returncode != 0:
    raise SystemExit("FATAL: cannot extract .pkg\n" + ext.stderr[-1500:])
log(f"extracted in {time.time()-t:.1f}s")

HERMES_BIN = pathlib.Path("/root/.local/bin/hermes")
if not HERMES_BIN.exists():
    raise SystemExit("FATAL: /root/.local/bin/hermes missing after extract")
os.chmod(HERMES_BIN, 0o755)
os.environ["PATH"] = "/root/.local/bin:/usr/local/bin:" + os.environ.get("PATH", "")
log("hermes: " + sh("/root/.local/bin/hermes --version 2>&1 | tail -1", timeout=180).stdout.strip())
'''

RESTORE = r'''
# ── 1b. persistent agent state: encrypted backup on branch `state` ─────────
import base64

GH_API = "https://api.github.com"
BR = SEC["backup"]["branch"]
BF = SEC["backup"]["file"]
KEY = pathlib.Path("/root/.backup.key")
KEY.write_text(SEC["backup"]["key"]); os.chmod(KEY, 0o600)

def gh(path, method="GET", body=None):
    req = urllib.request.Request(GH_API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"token {GH['token']}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "kaggle-sandbox"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

def ensure_branch():
    try:
        gh(f"/repos/{GH['repo']}/branches/{BR}"); return
    except Exception:
        pass
    base = gh(f"/repos/{GH['repo']}/git/ref/heads/{GH['branch']}")["object"]["sha"]
    try:
        gh(f"/repos/{GH['repo']}/git/refs", "POST", {"ref": f"refs/heads/{BR}", "sha": base})
    except Exception:
        pass

def _crypt(data, decrypt=False):
    args = ["openssl", "enc"] + (["-d"] if decrypt else []) + [
        "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
        "-in", "/dev/stdin", "-pass", f"file:{KEY}"]
    r = subprocess.run(args, input=data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace")[-300:])
    return r.stdout

def restore():
    t = time.time()
    try:
        blob = base64.b64decode(gh(f"/repos/{GH['repo']}/contents/{BF}?ref={BR}")["content"])
    except Exception as e:
        log(f"restore: no previous state ({str(e)[:80]})"); return
    try:
        tar = subprocess.run(["tar", "-C", str(HH), "-xzf", "-"], input=_crypt(blob, True),
                             capture_output=True)
        log(f"restore: -{len(blob)/1e3:.0f} kB -> agent state in {time.time()-t:.1f}s"
            + ("" if tar.returncode == 0 else f" (tar rc={tar.returncode})"))
    except Exception as e:
        log(f"restore: failed ({e})")

def backup(force=False):
    items = [p for p in ("memories", "skills", "sessions", "config.yaml", "auth.json", "state.db")
             if (HH / p).exists()]
    if not items:
        return
    tar = subprocess.run(["tar", "-C", str(HH), "-czf", "-", *items], capture_output=True)
    if not tar.stdout or len(tar.stdout) > 12_000_000:
        log(f"backup: skipped ({len(tar.stdout)} B raw)"); return
    enc = _crypt(tar.stdout)
    body = {"message": f"state backup {time.strftime('%FT%TZ', time.gmtime())}",
            "content": base64.b64encode(enc).decode(), "branch": BR}
    try:
        body["sha"] = gh(f"/repos/{GH['repo']}/contents/{BF}?ref={BR}")["sha"]
    except Exception:
        ensure_branch()
    try:
        gh(f"/repos/{GH['repo']}/contents/{BF}", "PUT", body)
        log(f"backup: {len(enc)/1e3:.0f} kB encrypted -> {BR}:{BF}")
    except Exception as e:
        log(f"backup: push failed ({str(e)[:120]})")

restore()
'''

CONFIG = r'''
# ── 2. credentials: written straight from the private secrets dataset ───────
HH.mkdir(parents=True, exist_ok=True)
env_lines = [
    "# generated at every boot from the private Kaggle secrets dataset",
    f"KAGGLE_USERNAME={SEC['kaggle']['username']}",
    f"KAGGLE_API_TOKEN={SEC['kaggle']['api_token']}",
    f"GITHUB_TOKEN={GH['token']}",
    f"PINGGY_TOKEN={PINGGY['token']}",
    f"TELEGRAM_BOT_TOKEN={TG['bot_token']}",
    f"TELEGRAM_CHAT_ID={TG['chat_id']}",
]
if LLM.get("api_key"):
    env_lines += [f"{LLM.get('env_var','OPENROUTER_API_KEY')}={LLM['api_key']}"]
(HH / ".env").write_text("\n".join(env_lines) + "\n")
os.chmod(HH / ".env", 0o600)

cfg = HH / "config.yaml"
if not cfg.exists():
    model = LLM.get("model", "anthropic/claude-sonnet-4.5")
    provider = LLM.get("provider", "openrouter")
    cfg.write_text(
        "# written once on first boot - edit freely, it survives in the encrypted backup\n"
        "display:\n  interface: cli\n"
        f"model:\n  provider: {provider}\n  name: {model}\n"
        "tools:\n  approval_mode: auto\n"
    )
log("credentials written to ~/.hermes/.env")
'''

SSHD = r'''
# ── 3. OpenSSH server - password auth, no SSH key anywhere ─────────────────
os.makedirs("/run/sshd", exist_ok=True)
KEYDIR = HH / "ssh"
KEYDIR.mkdir(parents=True, exist_ok=True)
for kind in ("ed25519", "rsa"):
    priv, pub = KEYDIR / f"ssh_host_{kind}", KEYDIR / f"ssh_host_{kind}.pub"
    if not priv.exists():
        bits = "-t rsa -b 3072" if kind == "rsa" else "-t ed25519"
        sh(f"ssh-keygen -q {bits} -N '' -f {priv}", timeout=120)
    shutil.copy(priv, f"/etc/ssh/ssh_host_{kind}")
    shutil.copy(pub,  f"/etc/ssh/ssh_host_{kind}.pub")
    os.chmod(f"/etc/ssh/ssh_host_{kind}", 0o600)
os.chmod("/etc/ssh/ssh_host_ed25519.pub", 0o644)

os.makedirs("/etc/ssh/sshd_config.d", exist_ok=True)
pathlib.Path("/etc/ssh/sshd_config.d/99-sandbox.conf").write_text("""\
Port 22
AddressFamily any
PermitRootLogin yes
PasswordAuthentication yes
PermitEmptyPasswords no
KbdInteractiveAuthentication no
UsePAM yes
X11Forwarding yes
AllowTcpForwarding yes
GatewayPorts no
ClientAliveInterval 30
ClientAliveCountMax 6
MaxSessions 20
PrintMotd no
AcceptEnv LANG LC_* TERM
Subsystem sftp /usr/lib/openssh/sftp-server
""")

pw = SSH["password"].replace("'", "")
sh(f"echo 'root:{pw}' | chpasswd", check=True)
sh("chsh -s /bin/bash root", timeout=60)
listen = sh("pgrep -x sshd >/dev/null && pkill -x sshd; sleep 1; /usr/sbin/sshd -f /etc/ssh/sshd_config")
time.sleep(2)
probe = sh("ss -ltn 2>/dev/null | grep -c ':22 ' || true")
log(f"sshd listening (sockets on :22 = {probe.stdout.strip()})")
'''

TUNNEL = r'''
# ── 4. Pinggy Pro TCP tunnel: fixed host + fixed port ─────────────────────
TUN = pathlib.Path("/root/bin/tunnel.sh")
TUN.parent.mkdir(parents=True, exist_ok=True)
TUN.write_text(f"""#!/usr/bin/env bash
# supervised: pinggy TCP tunnel, reconnects forever
while true; do
  ssh -p 443 -N -T \\
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \\
    -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \\
    -o ExitOnForwardFailure=yes -o ConnectTimeout=15 \\
    -R0:localhost:22 "tcp+{PINGGY['token']}@a.pinggy.io"
  echo "[tunnel] dropped rc=$? $(date -u +%FT%TZ)" >> {LOGSD}/tunnel.log
  sleep 5
done
""")
os.chmod(TUN, 0o755)
tun_log = open(LOGSD / "tunnel.log", "ab", buffering=0)
subprocess.Popen(["bash", str(TUN)], stdout=tun_log, stderr=tun_log, start_new_session=True)

def tunnel_ready(deadline=90):
    """End-to-end proof: connect to the PUBLIC host:port and read the SSH banner."""
    end = time.time() + deadline
    while time.time() < end:
        try:
            with socket.create_connection((PINGGY["host"], int(PINGGY["port"])), timeout=6) as s:
                s.settimeout(6)
                banner = s.recv(64)
                if banner.startswith(b"SSH-"):
                    return True, banner.decode(errors="replace").strip()
        except Exception:
            pass
        time.sleep(3)
    return False, ""

t = time.time()
ok, banner = tunnel_ready()
log(f"public endpoint {PINGGY['host']}:{PINGGY['port']} -> {banner or 'NOT REACHABLE'} ({time.time()-t:.0f}s)")
if not ok:
    log((LOGSD / "tunnel.log").read_text()[-1200:] if (LOGSD / "tunnel.log").exists() else "no tunnel log")
'''

RUN = r'''
# ── 5. announce + control loop (this is what keeps the kernel alive) ───────
boot = time.time() - T0
tg(
 "🟢 <b>SANDBOX READY</b>\n"
 f"<code>ssh root@{PINGGY['host']} -p {PINGGY['port']}</code>\n"
 f"Boot: <b>{boot:.0f}s</b>\n"
 f"Agent: <code>{sh('/root/.local/bin/hermes --version 2>&1 | head -1').stdout.strip()}</code>\n"
 "Tắt bằng GitHub Action → action <b>off</b>."
)
log("READY")

last_bk = 0.0
bad = 0
while True:
    time.sleep(25)
    try:
        url = f"{PUBLIC_STATE}?cb={int(time.time())}"
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "sandbox"})
        mode = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("mode", "on")
        bad = 0
    except Exception as e:
        bad += 1
        log(f"state poll failed ({bad}): {e}")
        if bad > 40:
            log("state source unreachable for too long - keeping the sandbox up")
            bad = 0
        continue
    if mode != "on":
        log(f"state.json mode={mode} -> shutting down")
        backup()
        break
    if time.time() - last_bk > 900:
        backup()
        last_bk = time.time()

tg("🔴 <b>SANDBOX STOPPED</b>\nKernel tự thoát theo cờ <code>state.json</code>.")
log("control loop finished - kernel will now complete normally")
'''

CELLS = [BOOT, EXTRACT, RESTORE, CONFIG, SSHD, TUNNEL, RUN]

nb = {
    "cells": [
        {"cell_type": "markdown", "id": "hdr", "metadata": {},
         "source": [
             "# Kaggle Sandbox — Hermes Agent + OpenSSH + Pinggy Pro\n",
             "\n",
             "**Không sửa notebook này bằng tay.** Nó được `scripts/sync_kernel.py` sinh ra từ repo\n",
             "`subelips/sandbox` và được GitHub Actions đẩy lên Kaggle.\n",
             "\n",
             "Boot: giải nén `.pkg` → ghi `.env` → bật sshd (password, không SSH key) → mở tunnel\n",
             "TCP cố định → thông báo Telegram → giữ kernel sống tới khi `state.json` = `off`.\n",
         ]},
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
for i, src in enumerate(CELLS, 1):
    nb["cells"].append({
        "cell_type": "code", "id": f"c{i}i", "metadata": {}, "execution_count": None,
        "outputs": [], "source": src.strip("\n").splitlines(True),
    })

out = pathlib.Path("kernel")
out.mkdir(exist_ok=True)
(out / "sandbox.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False))
(out / "kernel-metadata.json").write_text(json.dumps({
    "id": "maithanhtu/hermes-sandbox",
    "title": "hermes sandbox",
    "code_file": "sandbox.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": "true",
    "enable_gpu": "false",
    "enable_internet": "true",
    "dataset_sources": ["maithanhtu/sandbox-secrets", "maithanhtu/hermes-agent-pkg"],
    "competition_sources": [],
    "kernel_sources": [],
    "model_sources": [],
}, indent=1) + "\n")
print("kernel/ written")

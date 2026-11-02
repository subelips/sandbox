"""Generate the Kaggle sandbox notebook + kernel metadata.

Run:  python3 scripts/sync_kernel.py
Never hand-edit kernel/sandbox.ipynb - it is overwritten from here.
"""
import json
import pathlib

BOOT = r'''
# ═══════════════════════════════════════════════════════════════════════════
#  KAGGLE SANDBOX - BOOT (Hermes Agent + OpenSSH + Pinggy TCP)
#  Full agent tree from the .pkg dataset. Nothing skipped, nothing rebuilt.
#  Config + credentials come from the private secrets dataset, so no boot ever
#  needs reconfiguring. No backup, no extra branch, no SSH key.
# ═══════════════════════════════════════════════════════════════════════════
import base64, json, os, pathlib, shutil, socket, subprocess, sys, threading, time
import urllib.parse, urllib.request

T0 = time.time()
def log(m): print(f"[{time.time()-T0:7.1f}s] {m}", flush=True)

def sh(c, timeout=600, check=False):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {c}\nSTDOUT:{r.stdout[-1500:]}\nSTDERR:{r.stderr[-1500:]}")
    return r

IN = pathlib.Path("/kaggle/input")
def find(name, required=True):
    for p in IN.rglob(name):
        return p
    if required:
        raise SystemExit(f"FATAL: {name} not mounted under /kaggle/input")
    return None

SEC = json.loads(find("secrets.json").read_text())
PINGGY, TG, SSH, GH = SEC["pinggy"], SEC["telegram"], SEC["ssh"], SEC["github"]
LLM = SEC.get("llm") or {}
HH = pathlib.Path("/root/.hermes")
LOGSD = HH / "logs"
LOGSD.mkdir(parents=True, exist_ok=True)
API = "https://api.github.com"
PUBLIC_STATE = f"https://raw.githubusercontent.com/{GH['repo']}/main/state.json"
KERNEL = os.environ.get("KAGGLE_KERNEL_RUN_TYPE", "?")

def gh(path, method="GET", body=None):
    req = urllib.request.Request(API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"token {GH['token']}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "kaggle-sandbox"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

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

def die(msg):
    """Fail loudly: print everything useful, tell Telegram, end the kernel as ERROR."""
    log("FATAL: " + msg)
    try:
        for p in (LOGSD / "tunnel.log", LOGSD / "sshd.log"):
            if p.exists():
                print(f"--- {p} ---\n{p.read_text()[-2500:]}", flush=True)
    finally:
        tg(f"❌ <b>SANDBOX BOOT FAILED</b>\n<pre>{msg[:900]}</pre>", silent=False)
        sys.stdout.flush()
        raise SystemExit(1)

def watchdog(seconds=900):
    def _boom():
        die(f"boot did not reach READY within {seconds}s")
    t = threading.Timer(seconds, _boom)
    t.daemon = True
    t.start()
    return t

WD = watchdog(900)
log(f"secrets loaded · kernel={KERNEL} · python={sys.version.split()[0]}")
'''

EXTRACT = r'''
# ── 1. full agent tree from the .pkg dataset (no reinstall, no network) ─────
pkg = find("hermes-agent-full.pkg")
log(f"pkg: {pkg} ({pkg.stat().st_size/1e6:.0f} MB)")

z = None
zb = pkg.parent / "zstd"
if zb.exists():
    pathlib.Path("/root/bin").mkdir(parents=True, exist_ok=True)
    shutil.copy(zb, "/root/bin/zstd"); os.chmod("/root/bin/zstd", 0o755)
    v = sh("/root/bin/zstd --version", timeout=60)
    if v.returncode == 0:
        z = "/root/bin/zstd"
        log("bundled zstd: " + v.stdout.strip().splitlines()[0])
    else:
        log("bundled zstd unusable: " + v.stderr.strip()[:200])
if not z and shutil.which("zstd"):
    z = "zstd"
if not z:
    log("no zstd -> apt-get")
    sh("apt-get install -y -qq zstd || (apt-get update -qq && apt-get install -y -qq zstd)", timeout=300)
    z = "/usr/bin/zstd" if os.path.exists("/usr/bin/zstd") else None

t = time.time()
ext = sh(f'"{z}" -dc "{pkg}" | tar -C / -xf -', timeout=1200) if z else sh(f'gzip -dc "{pkg}" | tar -C / -xf -', timeout=1200)
log(f"tar rc={ext.returncode} in {time.time()-t:.1f}s")
if ext.returncode != 0:
    die(f"extract failed rc={ext.returncode}: {ext.stderr[-800:]}")

HERMES_BIN = pathlib.Path("/root/.local/bin/hermes")
if not HERMES_BIN.exists():
    die("/root/.local/bin/hermes missing after extract")
os.chmod(HERMES_BIN, 0o755)
os.environ["PATH"] = "/root/.local/bin:/usr/local/bin:" + os.environ.get("PATH", "")
log("hermes: " + sh("/root/.local/bin/hermes --version 2>&1 | head -1", timeout=240).stdout.strip())
'''

CONFIG = r'''
# ── 2. config + credentials, straight from the private secrets dataset ─────
# The dataset is the single source of truth: config.yaml there always wins.
cfg_src = find("hermes-config.yaml", required=False)
if cfg_src:
    shutil.copy(cfg_src, HH / "config.yaml")
    os.chmod(HH / "config.yaml", 0o644)
    log(f"config.yaml <- dataset ({cfg_src.stat().st_size} B) · nothing to configure")
else:
    log("config.yaml: dataset has no hermes-config.yaml, keeping the installer's")

env_lines = [
    "# rewritten at every boot from the private Kaggle secrets dataset",
    f"KAGGLE_USERNAME={SEC['kaggle']['username']}",
    f"KAGGLE_API_TOKEN={SEC['kaggle']['api_token']}",
    f"KAGGLE_DATASET={SEC['kaggle'].get('secrets_dataset', '')}",
    f"GITHUB_TOKEN={GH['token']}",
    f"PINGGY_TOKEN={PINGGY['token']}",
    f"TELEGRAM_BOT_TOKEN={TG['bot_token']}",
    f"TELEGRAM_CHAT_ID={TG['chat_id']}",
]
if LLM.get("api_key"):
    env_lines.append(f"{LLM.get('env_var', 'OPENROUTER_API_KEY')}={LLM['api_key']}")
(HH / ".env").write_text("\n".join(env_lines) + "\n")
os.chmod(HH / ".env", 0o600)

# make `hermes` reachable from every session (login shell, exec_command, cron)
pathlib.Path("/usr/local/bin/hermes").write_text("#!/bin/sh\nexec /root/.local/bin/hermes \"$@\"\n")
os.chmod("/usr/local/bin/hermes", 0o755)
pathlib.Path("/etc/profile.d/10-sandbox.sh").write_text("export PATH=/root/.local/bin:$PATH\n")
os.chmod("/etc/profile.d/10-sandbox.sh", 0o644)

# push live config changes back into the dataset, so the next boot keeps them
SAVE_SH = """#!/bin/sh
# hermes-save-config - day ~/.hermes/config.yaml hien tai vao dataset secret
set -eu
. /root/.hermes/.env
D=$(mktemp -d)
if ! python3 -c 'import kaggle' 2>/dev/null; then
  pip install -q kaggle six python-dateutil tqdm >/dev/null 2>&1 || true
fi
python3 -m kaggle datasets download -d "$KAGGLE_DATASET" -p "$D" --unzip -q
cp /root/.hermes/config.yaml "$D/hermes-config.yaml"
printf '{"title":"sandbox secrets","id":"%s","licenses":[{"name":"CC0-1.0"}]}' "$KAGGLE_DATASET" > "$D/dataset-metadata.json"
python3 -m kaggle datasets version -p "$D" -m "config $(date -u +%FT%TZ)" -r zip -q
echo "config saved -> $KAGGLE_DATASET"
"""
save = pathlib.Path("/usr/local/bin/hermes-save-config")
save.write_text(SAVE_SH)
os.chmod(save, 0o755)
log("credentials -> ~/.hermes/.env · hermes on PATH · hermes-save-config ready")
'''

SSHD = r'''
# ── 3. OpenSSH server, password auth, no SSH key anywhere ─────────────────
# The image ships its own sshd config (127.0.0.1:2222) and we must not fight
# it or kill it, so this runs a SECOND, fully self-contained sshd on :22 with
# its own config file, its own host keys and its own pid file.
os.makedirs("/run/sshd", exist_ok=True)
KEYDIR = HH / "ssh"; KEYDIR.mkdir(parents=True, exist_ok=True)
for kind in ("ed25519", "rsa"):
    priv = KEYDIR / f"ssh_host_{kind}"
    if not priv.exists():
        bits = "-t rsa -b 3072" if kind == "rsa" else "-t ed25519"
        sh(f"ssh-keygen -q {bits} -N '' -f {priv}", timeout=180, check=True)
    # keep the same host identity in /etc/ssh too, so Termius never re-prompts
    shutil.copy(priv, f"/etc/ssh/ssh_host_{kind}")
    shutil.copy(str(priv) + ".pub", f"/etc/ssh/ssh_host_{kind}.pub")
    os.chmod(f"/etc/ssh/ssh_host_{kind}", 0o600)

CONF = KEYDIR / "sshd_config"
CONF.write_text(f"""\
PidFile /run/sandbox-sshd.pid
Port 22
ListenAddress 0.0.0.0
HostKey {KEYDIR}/ssh_host_ed25519
HostKey {KEYDIR}/ssh_host_rsa
PermitRootLogin yes
PasswordAuthentication yes
PermitEmptyPasswords no
KbdInteractiveAuthentication no
UsePAM yes
AllowTcpForwarding yes
X11Forwarding yes
ClientAliveInterval 30
ClientAliveCountMax 6
MaxSessions 20
MaxStartups 30:30:100
PrintMotd no
AcceptEnv LANG LC_* TERM
Subsystem sftp /usr/lib/openssh/sftp-server
""")

chk = sh(f"/usr/sbin/sshd -t -f {CONF}")
if chk.returncode:
    die("sshd config invalid: " + chk.stderr[-700:])

pidf = pathlib.Path("/run/sandbox-sshd.pid")
if pidf.exists():
    sh(f"kill {pidf.read_text().strip()} 2>/dev/null || true"); time.sleep(1)

pw = SSH["password"].replace("'", "")
if sh(f"echo 'root:{pw}' | chpasswd").returncode:
    die("chpasswd failed")
started = sh(f"/usr/sbin/sshd -f {CONF} -E {LOGSD}/sshd.log")
time.sleep(2)

def local_ssh_banner(wait=25):
    end = time.time() + wait
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", 22), timeout=4) as s:
                s.settimeout(4); b = s.recv(64)
                if b.startswith(b"SSH-"): return b.decode(errors="replace").strip()
        except Exception:
            time.sleep(1)
    return ""

banner = local_ssh_banner()
if not banner:
    die("sshd not answering on 127.0.0.1:22 (rc=" + str(started.returncode) + ") " + started.stderr[-500:])
log(f"sshd up on 0.0.0.0:22: {banner}")
'''

TUNNEL = r'''
# ── 4. Pinggy Pro TCP tunnel: fixed host, fixed port ──────────────────────
TUN = pathlib.Path("/root/bin/tunnel.sh")
TUN.parent.mkdir(parents=True, exist_ok=True)
TUN.write_text(f"""#!/usr/bin/env bash
while true; do
  ssh -p 443 -N -T \\
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \\
    -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \\
    -o ExitOnForwardFailure=yes -o ConnectTimeout=15 \\
    -R0:127.0.0.1:22 "tcp+{PINGGY['token']}@a.pinggy.io"
  echo "[tunnel] dropped rc=$? $(date -u +%FT%TZ)" >> {LOGSD}/tunnel.log
  sleep 5
done
""")
os.chmod(TUN, 0o755)
tlog = open(LOGSD / "tunnel.log", "ab", buffering=0)
subprocess.Popen(["bash", str(TUN)], stdout=tlog, stderr=tlog, start_new_session=True)

def public_banner(deadline=100):
    """End-to-end proof: public host:port must answer with OUR sshd banner."""
    end = time.time() + deadline
    while time.time() < end:
        try:
            with socket.create_connection((PINGGY["host"], int(PINGGY["port"])), timeout=8) as s:
                s.settimeout(8); b = s.recv(64)
                if b.startswith(b"SSH-"): return b.decode(errors="replace").strip()
        except Exception:
            pass
        time.sleep(3)
    return ""

t = time.time()
pub = public_banner()
if not pub:
    tail = (LOGSD / "tunnel.log").read_text()[-900:] if (LOGSD / "tunnel.log").exists() else "(no log)"
    die(f"public endpoint {PINGGY['host']}:{PINGGY['port']} not answering after {time.time()-t:.0f}s | {tail}")
log(f"public tunnel live in {time.time()-t:.0f}s: {pub}")
'''

RUN = r'''
# ── 5. announce + control loop (this keeps the kernel alive) ──────────────
boot = time.time() - T0
WD.cancel()
ver = sh("/root/.local/bin/hermes --version 2>&1 | head -1").stdout.strip()
tg(
 "🟢 <b>SANDBOX READY</b>\n"
 f"<code>ssh root@{PINGGY['host']} -p {PINGGY['port']}</code>\n"
 f"Boot: <b>{boot:.0f}s</b>\n"
 f"Agent: <code>{ver}</code>\n"
 "Tắt: GitHub Action → <b>off</b>."
)
log(f"READY in {boot:.0f}s")

def read_mode():
    """Control plane read: the API, then raw as a fallback.
    raw.githubusercontent.com sits behind a CDN that served a 5-minute-stale
    copy in testing, which is why the API is the primary source."""
    try:
        blob = base64.b64decode(gh(f"/repos/{GH['repo']}/contents/state.json?ref={GH['branch']}")["content"])
        return json.loads(blob).get("mode", "on")
    except Exception as e:
        log(f"api state read failed: {str(e)[:80]}")
    req = urllib.request.Request(f"{PUBLIC_STATE}?cb={int(time.time())}",
                                 headers={"Cache-Control": "no-cache", "User-Agent": "sandbox"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read()).get("mode", "on")

fail = 0
while True:
    time.sleep(15)
    try:
        mode = read_mode()
        fail = 0
    except Exception as e:
        fail += 1
        log(f"state read failed ({fail}): {e}")
        if fail > 60:
            log("state source unreachable for 15 min - keeping sandbox up"); fail = 0
        continue
    if mode != "on":
        log(f"state.json mode={mode} -> shutting down")
        break

tg("🔴 <b>SANDBOX STOPPED</b>\nKernel tự thoát theo cờ <code>state.json</code>.", silent=False)
log("control loop finished - kernel completes now")
'''

CELLS = [
    ("boot", BOOT), ("extract", EXTRACT), ("config", CONFIG),
    ("sshd", SSHD), ("tunnel", TUNNEL), ("run", RUN),
]

nb = {
    "cells": [{
        "cell_type": "markdown", "id": "hdr", "metadata": {},
        "source": [
            "# Kaggle Sandbox — Hermes Agent + OpenSSH + Pinggy Pro\n",
            "\n",
            "Sinh tự động bởi `scripts/sync_kernel.py` từ repo `subelips/sandbox`.\n",
            "Đừng sửa tay: lần `kaggle kernels push` sau sẽ ghi đè.\n",
            "\n",
            "`secrets.json` + `hermes-config.yaml` ← dataset `maithanhtu/sandbox-secrets` (private).\n",
            "`hermes-agent-full.pkg` ← dataset `maithanhtu/hermes-agent-pkg` (tar+zstd, bản cài đầy đủ).\n",
        ]}],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4, "nbformat_minor": 5,
}
for name, src in CELLS:
    nb["cells"].append({
        "cell_type": "code", "id": name, "metadata": {}, "execution_count": None,
        "outputs": [], "source": src.strip("\n").splitlines(True),
    })

out = pathlib.Path(__file__).resolve().parent.parent / "kernel"
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
print(f"kernel/ written ({len(CELLS)} cells)")

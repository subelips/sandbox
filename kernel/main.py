#!/usr/bin/env python3
"""Kaggle sandbox entrypoint. Secrets are read directly from the private Kaggle Dataset."""
import json
import os
import pwd
import shutil
import tarfile
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RUNTIME_DATASET_DIR = Path(os.environ.get("RUNTIME_DATASET_DIR", "/kaggle/input/hermes-runtime"))
RUNTIME_BUNDLE = RUNTIME_DATASET_DIR / "hermes-runtime.tar.gz"
SECRET_CONFIG_DIR = SECRET_DATASET_DIR / "hermes-config"

SECRET_DATASET_DIR = Path(os.environ.get(
    "SECRET_DATASET_DIR", "/kaggle/input/hermes-secret-store"
))
SECRET_FILE = Path(os.environ.get(
    "SECRET_FILE", str(SECRET_DATASET_DIR / "secrets.json")
))

def log(message):
    print(f"[sandbox] {message}", flush=True)

def load_dataset_secrets():
    if not SECRET_FILE.is_file():
        raise RuntimeError(
            f"Secret file not found: {SECRET_FILE}. Attach the private "
            "hermes-secret-store Dataset and include secrets.json."
        )
    try:
        data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("Cannot parse Dataset secrets.json") from exc
    if not isinstance(data, dict):
        raise RuntimeError("secrets.json must contain a JSON object")
    required = ("PINGGY_TOKEN", "SSH_PASSWORD", "NTFY_TOPIC")
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise RuntimeError("Missing required keys in Dataset secrets.json: " + ", ".join(missing))
    # Keep secret values in memory only; never print them.
    return {key: str(value).strip() for key, value in data.items()}

SECRETS = load_dataset_secrets()
PINGGY_TOKEN = SECRETS["PINGGY_TOKEN"]
SSH_PASSWORD = SECRETS["SSH_PASSWORD"]
NTFY_TOPIC = SECRETS["NTFY_TOPIC"]
REMOTE_PORT = str(SECRETS.get("PINGGY_REMOTE_PORT", "19326")).strip()
PINGGY_HOST = str(SECRETS.get("PINGGY_HOST", "sandboxx.a.pinggy.link")).strip()
PINGGY_GATEWAY = str(SECRETS.get("PINGGY_GATEWAY", "pro.pinggy.io")).strip()

if not REMOTE_PORT.isdigit() or not (1024 <= int(REMOTE_PORT) <= 65535):
    raise RuntimeError("PINGGY_REMOTE_PORT must be a valid TCP port")

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def ensure_packages():
    if not Path("/usr/sbin/sshd").exists():
        log("Installing OpenSSH server")
        run(["apt-get", "update", "-qq"])
        run(["apt-get", "install", "-y", "-qq", "openssh-server", "curl", "ca-certificates"])
    Path("/run/sshd").mkdir(parents=True, exist_ok=True)

def configure_ssh():
    try:
        pwd.getpwnam("sandbox")
    except KeyError:
        run(["useradd", "--create-home", "--shell", "/bin/bash", "sandbox"])
    run(["chpasswd"], input=f"sandbox:{SSH_PASSWORD}\n", text=True)
    ssh_config = """Port 22
AddressFamily inet
ListenAddress 0.0.0.0
PermitRootLogin no
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication no
UsePAM yes
AllowUsers sandbox
X11Forwarding no
AllowAgentForwarding no
PermitTunnel no
AllowTcpForwarding no
GatewayPorts no
ClientAliveInterval 60
ClientAliveCountMax 2
"""
    Path("/etc/ssh/sshd_config.d/90-kaggle-sandbox.conf").write_text(ssh_config)
    run(["/usr/sbin/sshd", "-t"])
    return subprocess.Popen(["/usr/sbin/sshd", "-D", "-e"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def restore_runtime():
    """Restore the prebuilt Hermes installation bundle, if the Dataset has one."""
    home = Path("/home/sandbox")
    if not RUNTIME_BUNDLE.is_file():
        log("No prebuilt runtime bundle found; doing one-time online bootstrap")
        return False
    log(f"Restoring prebuilt Hermes runtime from {RUNTIME_BUNDLE}")
    with tarfile.open(RUNTIME_BUNDLE, "r:gz") as archive:
        base = home.resolve()
        for member in archive.getmembers():
            destination = (home / member.name).resolve()
            if destination != base and base not in destination.parents:
                raise RuntimeError("Unsafe path in Hermes runtime archive")
        archive.extractall(home)
    account = pwd.getpwnam("sandbox")
    for root, dirs, files in os.walk(home):
        os.chown(root, account.pw_uid, account.pw_gid)
        for name in dirs + files:
            os.chown(os.path.join(root, name), account.pw_uid, account.pw_gid)
    launcher = home / ".local/bin/hermes"
    source = home / ".hermes/hermes-agent"
    if not launcher.exists() or not source.is_dir():
        raise RuntimeError("Runtime archive is incomplete: expected .local/bin/hermes and .hermes/hermes-agent")
    log("Prebuilt Hermes source, launcher and managed runtime restored")
    return True

def restore_secret_config():
    """Copy personal Hermes config and credentials from the private secret Dataset."""
    target = Path("/home/sandbox/.hermes")
    if not SECRET_CONFIG_DIR.is_dir():
        log("No hermes-config folder in secret Dataset; keeping default Hermes config")
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in SECRET_CONFIG_DIR.iterdir():
        if item.is_file() and item.name in {"config.yaml", ".env"}:
            destination = target / item.name
            shutil.copy2(item, destination)
            os.chmod(destination, 0o600)
    account = pwd.getpwnam("sandbox")
    for name in ("config.yaml", ".env"):
        path = target / name
        if path.exists():
            os.chown(path, account.pw_uid, account.pw_gid)
    log("Hermes config and credentials restored from private secret Dataset")

def export_runtime():
    """Export installed Hermes code and managed tools, excluding personal config."""
    home = Path("/home/sandbox")
    output_dir = Path("/kaggle/working/hermes-runtime-export")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / "hermes-runtime.tar.gz"
    include = [home / ".local", home / ".cache", home / ".hermes/hermes-agent"]
    available = [path for path in include if path.exists()]
    if not (home / ".local/bin/hermes").exists() or not (home / ".hermes/hermes-agent").is_dir():
        log("Runtime export skipped: Hermes installation is incomplete")
        return
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in available:
            archive.add(path, arcname=str(path.relative_to(home)), recursive=True)
    log(f"Prebuilt runtime bundle exported to {archive_path}")
    log("Upload hermes-runtime.tar.gz as a new version of the private hermes-runtime Dataset")
def install_hermes():
    home = Path("/home/sandbox")
    marker = home / ".hermes" / "config.yaml"
    if marker.exists() and (home / ".local/bin/hermes").exists():
        log("Hermes already present in this runtime")
        return
    log("Installing official Hermes Agent for user sandbox")
    env = os.environ.copy()
    env.update({"HOME": str(home), "USER": "sandbox", "LOGNAME": "sandbox",
                "PATH": f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin"})
    account = pwd.getpwnam("sandbox")
    def demote_to_sandbox():
        os.initgroups("sandbox", account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    installer = subprocess.Popen(
        ["bash", "-lc", "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"],
        cwd=str(home), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, preexec_fn=demote_to_sandbox)
    for line in installer.stdout:
        log("Hermes installer: " + line.rstrip()[-400:])
    if installer.wait() != 0:
        raise RuntimeError("Official Hermes installer failed")
    log("Hermes installed. Configure provider from Termius with: hermes model")

def publish(message):
    url = f"https://ntfy.sh/{urllib.parse.quote(NTFY_TOPIC, safe='')}"
    req = urllib.request.Request(url, data=message.encode(), method="POST",
                                headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()

def poll_stop(since):
    url = f"https://ntfy.sh/{urllib.parse.quote(NTFY_TOPIC, safe='')}/json?poll=1&since={since}"
    req = urllib.request.Request(url, headers={"User-Agent": "kaggle-sandbox/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            for raw in response:
                try:
                    event = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                if event.get("event") == "message" and event.get("message", "").strip() == "STOP":
                    return True
    except Exception as exc:
        log(f"ntfy poll retry: {type(exc).__name__}")
    return False

def main():
    ensure_packages()
    restored = restore_runtime()
    if not restored:
        install_hermes()
    restore_secret_config()
    sshd = configure_ssh()
    since = int(time.time())
    log(f"Starting Pinggy reverse SSH tunnel for {PINGGY_HOST}:{REMOTE_PORT}")
    pinggy_args = [
        "ssh", "-p", "443", "-N", "-T",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=no",
        "-R", f"{PINGGY_HOST}:{REMOTE_PORT}:127.0.0.1:22",
        f"{PINGGY_TOKEN}+tcp@{PINGGY_GATEWAY}",
    ]
    tunnel = subprocess.Popen(pinggy_args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        publish(f"STARTED {PINGGY_HOST}:{REMOTE_PORT}")
        log(f"Sandbox started. SSH user: sandbox; host: {PINGGY_HOST}; port: {REMOTE_PORT}")
        while True:
            if sshd.poll() is not None:
                raise RuntimeError("sshd exited unexpectedly")
            if tunnel.poll() is not None:
                log("Pinggy tunnel disconnected; reconnecting")
                tunnel = subprocess.Popen(pinggy_args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            if poll_stop(since):
                log("STOP received; shutting down services")
                break
            time.sleep(2)
    finally:
        for proc in (tunnel, sshd):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        export_runtime()
        log("Sandbox stopped")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"FATAL: {type(exc).__name__}: {exc}")
        sys.exit(1)

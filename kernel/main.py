#!/usr/bin/env python3
"""Kaggle sandbox entrypoint. Credentials are read only from Kaggle Secrets."""
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

def log(message):
    print(f"[sandbox] {message}", flush=True)

def secret(name):
    try:
        from kaggle_secrets import UserSecretsClient
        value = UserSecretsClient().get_secret(name)
    except Exception as exc:
        raise RuntimeError(f"Missing or unreadable Kaggle Secret: {name}") from exc
    if not value:
        raise RuntimeError(f"Kaggle Secret is empty: {name}")
    return value.strip()

PINGGY_TOKEN = secret("PINGGY_TOKEN")
SSH_PASSWORD = secret("SSH_PASSWORD")
NTFY_TOPIC = secret("NTFY_TOPIC")
REMOTE_PORT = os.environ.get("PINGGY_REMOTE_PORT", "19326")
PINGGY_HOST = os.environ.get("PINGGY_HOST", "sandboxx.a.pinggy.link")
PINGGY_GATEWAY = os.environ.get("PINGGY_GATEWAY", "pro.pinggy.io")

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
    return subprocess.Popen(["/usr/sbin/sshd", "-D", "-e"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

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
    sshd = configure_ssh()
    install_hermes()
    since = int(time.time())
    log(f"Starting Pinggy reverse SSH tunnel for {PINGGY_HOST}:{REMOTE_PORT}")
    log("Expected Termius endpoint uses the reserved Pinggy hostname and port.")
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
        log("Sandbox started. Termius SSH user: sandbox")
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
        log("Sandbox stopped")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"FATAL: {type(exc).__name__}: {exc}")
        sys.exit(1)

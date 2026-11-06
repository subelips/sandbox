# Hermes Kaggle Sandbox (iPhone + Termius + Pinggy Pro)

This repository deploys a private Kaggle script kernel and controls it through one GitHub Actions workflow with START / STOP.

- GitHub repository: subelips/sandbox
- Kaggle kernel: maithanhtu/hermes-kaggle-sandbox
- Pinggy hostname configured in the runtime: sandboxx.a.pinggy.link
- Reserved Pinggy remote port: 19326
- SSH username: sandbox
- SSH authentication: password (no SSH key)

## Important limitations

1. Kaggle is an ephemeral notebook runtime, not a 24/7 VPS. Kaggle may stop a session because of runtime limits, quotas, inactivity, or platform policy. The workflow starts a kernel; it cannot guarantee continuous uptime.
2. STOP is cooperative: GitHub Actions publishes a private ntfy message and the running kernel polls for it. It is not an instant hard-stop API.
3. Hermes is installed from the official installer at runtime. This initial deployment does not yet build a reusable .pkg cache dataset or persist ~/.hermes between Kaggle sessions. Do not assume config, OAuth credentials, chat history, memories, cron jobs, or custom skills survive a restart.
4. Never put credentials in this repository, a Kaggle dataset, notebook source, or chat messages.

## A. Add GitHub Actions Secrets

In GitHub, open Settings → Secrets and variables → Actions → New repository secret and add:

| Secret | Value |
|---|---|
| KAGGLE_USERNAME | Your Kaggle username: maithanhtu |
| KAGGLE_KEY | A newly generated Kaggle API key (JSON token/key value only) |
| NTFY_TOPIC | A long, random, private topic name (do not reuse the public word sandbox) |

Do not paste these values into ChatGPT or commit them.

## B. Create and attach Kaggle Secrets

The Kaggle kernel must have these secrets attached in its Add-ons → Secrets panel:

| Kaggle Secret name | Value |
|---|---|
| PINGGY_TOKEN | Your current Pinggy Pro token |
| SSH_PASSWORD | A long, unique password for the Linux user sandbox |
| NTFY_TOPIC | Exactly the same private topic used in GitHub Actions |

The Kaggle secret named NTFY_TOPIC is separate from the GitHub Actions secret with the same name. Add it to Kaggle manually; GitHub Actions cannot read Kaggle Secrets.

First-time bootstrap: the first START push may create the Kaggle kernel but its first run can fail because the kernel has no attached secrets yet. Open the new kernel in Kaggle, add the three secrets above under Add-ons → Secrets, then run START again from GitHub Actions.

## C. Verify Pinggy Pro reservation

In the Pinggy dashboard, confirm that the token is authorized for the exact TCP hostname sandboxx.a.pinggy.link and remote port 19326. The runtime asks Pinggy for this mapping using the SSH remote-forward form:

    ssh -p 443 -N -T -R sandboxx.a.pinggy.link:19326:127.0.0.1:22 TOKEN+tcp@pro.pinggy.io

Do not expose the token. If Pinggy shows a different gateway, domain syntax, or assigned port, update the runtime configuration before START. A reserved remote port does not by itself prove that the hostname-to-port mapping is configured correctly.

## D. Start and stop

1. Open the repository's Actions tab.
2. Select Kaggle Sandbox → Run workflow.
3. Choose START and run it.
4. Wait for the Kaggle kernel to start. The runtime installs OpenSSH and the official Hermes Agent, then opens the Pinggy reverse tunnel.
5. In Termius, create an SSH host:
   - Host: sandboxx.a.pinggy.link
   - Port: 19326
   - Username: sandbox
   - Password: the value stored in Kaggle Secret SSH_PASSWORD
6. Once connected, Hermes is available to the sandbox user. Run:

    export PATH="$HOME/.local/bin:$PATH"
    hermes model

Configure your model provider and API credentials interactively. Hermes keeps secrets in ~/.hermes/.env and settings in ~/.hermes/config.yaml; protect both. Do not use hermes setup --portal unless you intend to complete its OAuth flow in the Termius session.

To stop, run the same workflow again and choose STOP. The running kernel receives the ntfy message and terminates the SSH server and Pinggy tunnel.

## E. Security notes

- Keep the ntfy topic random and private; anyone who knows it can publish to it.
- Rotate any credential that has ever been pasted into a chat or committed.
- SSH root login, public-key login, X11 forwarding, agent forwarding, and SSH TCP forwarding are disabled in this runtime. Only the dedicated sandbox account is allowed.
- The SSH password is injected from Kaggle Secrets at boot and is never written to the repository.
- The Pinggy TCP endpoint is publicly reachable. Use a unique strong SSH password and do not expose it.

## Files

- .github/workflows/sandbox.yml: one workflow with START and STOP choices.
- kernel/kernel-metadata.json: Kaggle kernel metadata.
- kernel/main.py: runtime bootstrap, SSH, Pinggy tunnel, and ntfy STOP polling.

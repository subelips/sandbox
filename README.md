# Hermes Kaggle Sandbox (iPhone + Termius + Pinggy Pro)

One fixed Kaggle script kernel is controlled by one GitHub Actions workflow with START / STOP. The kernel mounts three separate private Kaggle Datasets: a prebuilt Hermes runtime, a package cache, and a secret/configuration store.

- GitHub repository: subelips/sandbox
- Current kernel metadata ID: maithanhtu/sandbox
- Pinggy hostname: sandboxx.a.pinggy.link
- Reserved Pinggy remote port: 19326
- SSH username: sandbox
- SSH authentication: password

## 1. Create the three private Kaggle Datasets first

Create both datasets from the Kaggle mobile website. Keep them **Private**.

### Dataset A — package cache

- Title: Hermes Package Cache
- Slug: `hermes-package-cache`
- Owner: `maithanhtu`
- Dataset URL: `maithanhtu/hermes-package-cache`

This Dataset is for downloaded dependency archives and package caches with the `.pkg` suffix (plus wheels or other offline package files). It is separate from the Hermes source/runtime bundle. Do not upload credentials here. The current bootstrap does not yet directly consume every possible `.pkg` format; package-cache integration must match the actual archive format and Hermes PM cache layout.

### Dataset B — secrets store

- Title: Hermes Secret Store
- Slug: `hermes-secret-store`
- Owner: `maithanhtu`
- Dataset URL: `maithanhtu/hermes-secret-store`

Upload exactly one file at the dataset root named `secrets.json` with this structure (replace every placeholder on your iPhone before uploading):

```json
{
  "PINGGY_TOKEN": "PUT_YOUR_CURRENT_PINGGY_TOKEN_HERE",
  "SSH_PASSWORD": "CREATE_A_LONG_UNIQUE_PASSWORD",
  "NTFY_TOPIC": "USE_A_LONG_RANDOM_PRIVATE_TOPIC",
  "PINGGY_HOST": "sandboxx.a.pinggy.link",
  "PINGGY_REMOTE_PORT": "19326",
  "PINGGY_GATEWAY": "pro.pinggy.io"
}
```

The Notebook reads this file directly from:
`/kaggle/input/hermes-secret-store/secrets.json`

Also place personal Hermes configuration in a folder named `hermes-config/` at the Dataset root. Put `config.yaml` and `.env` inside it:

```
hermes-secret-store/
  secrets.json
  hermes-config/
    config.yaml
    .env
```

At boot, the Notebook copies `hermes-config/config.yaml` and `hermes-config/.env` into `/home/sandbox/.hermes/` with restrictive file permissions. Keep all model-provider API keys, OAuth tokens, and personal Hermes configuration in this private Dataset. It does **not** use Kaggle Secrets. Never put the actual contents of `secrets.json` in GitHub, a public dataset, or a ChatGPT message. Keep the Dataset private and limit access to your own account. Anyone who can access this private Dataset or the running kernel may be able to obtain its secrets; private does not mean encrypted.

### Dataset C — Hermes Runtime (complete installation bundle)

- Title: Hermes Runtime
- Slug: `hermes-runtime`
- Owner: `maithanhtu`
- Dataset URL: `maithanhtu/hermes-runtime`

This Dataset is **not** for chat history or personal configuration. It is the offline installation bundle: the Hermes Agent source tree, launcher, managed Python environment, PM-managed tools, and downloaded runtime assets produced by the initial successful install.

The expected file at the Dataset root is:

```
hermes-runtime.tar.gz
```

The Notebook restores this archive into `/home/sandbox`. On the first boot, if the archive does not exist yet, it performs the official online Hermes installation once. On a normal cooperative STOP, it exports `/kaggle/working/hermes-runtime-export/hermes-runtime.tar.gz`. Download that archive from the Kaggle Kernel output and upload it as a new version of the private `hermes-runtime` Dataset. Future starts restore the prebuilt bundle rather than rerunning the Hermes installer and downloading its managed runtime again.

The archive includes `~/.local`, `~/.cache`, and `~/.hermes/hermes-agent`. It deliberately excludes personal Hermes config and credentials; those belong in Dataset B. This bundle is tied to the Kaggle Linux architecture and compatible system libraries. A change in Hermes version, Python/Node runtime, or Kaggle base image may require rebuilding it. Some optional integrations may still download their own components when first used.

## 2. Attach the datasets to the fixed kernel

The repository metadata already lists these dataset sources:

- `maithanhtu/hermes-package-cache`
- `maithanhtu/hermes-secret-store`
- `maithanhtu/hermes-runtime`

Create all three datasets before running START. If either slug differs, correct `kernel/kernel-metadata.json` in GitHub to match the actual dataset slug. The Kaggle kernel metadata currently targets `maithanhtu/sandbox`; keep that same ID for subsequent updates so the workflow updates the same kernel.

## 3. GitHub Actions credentials

In GitHub, open Settings → Secrets and variables → Actions and add:

| Secret | Value |
|---|---|
| `KAGGLE_USERNAME` | `maithanhtu` |
| `KAGGLE_KEY` | Your newly generated Kaggle API key |
| `NTFY_TOPIC` | The exact same random topic stored in Dataset B |

These are GitHub Actions secrets used by the workflow. The Notebook's Pinggy token, SSH password, and ntfy topic are read from Dataset B. Do not paste any credential into this repository.

## 4. Verify Pinggy Pro

In the Pinggy dashboard, confirm that your current token supports the reserved TCP hostname `sandboxx.a.pinggy.link` and remote port `19326`. Confirm the gateway and remote-forward syntax shown in your own Pinggy dashboard before starting. The current code defaults to `pro.pinggy.io`; if your dashboard shows a different gateway, change `PINGGY_GATEWAY` in Dataset B.

## 5. Start and connect from iPhone

1. Open this repository's Actions tab.
2. Choose **Kaggle Sandbox → Run workflow → START**.
3. Wait for the Kaggle kernel to install OpenSSH and the official Hermes Agent and establish the Pinggy tunnel.
4. In Termius, create an SSH connection:
   - Host: `sandboxx.a.pinggy.link`
   - Port: `19326`
   - Username: `sandbox`
   - Password: the `SSH_PASSWORD` value in Dataset B
5. After connecting, run:

```bash
export PATH="$HOME/.local/bin:$PATH"
hermes model
```

Configure the model/provider and Hermes credentials inside the SSH session. Hermes stores configuration under `~/.hermes/`.

To stop, run the same GitHub Actions workflow and choose **STOP**. The running kernel polls the ntfy topic and exits cooperatively after receiving STOP.

## Important limits and security

- Kaggle is an ephemeral runtime, not a guaranteed 24/7 VPS. Kaggle can stop sessions due to runtime limits, quotas, inactivity, or platform policy.
- STOP is cooperative, not an instant hard-stop API.
- The runtime Dataset restores the prebuilt Hermes installation bundle. The first build still needs internet; subsequent boots can restore the bundle offline. The exported bundle is produced only on cooperative STOP, so abrupt termination can prevent export.
- The package-cache Dataset is attached; its exact `.pkg` format still needs to be wired to the matching Hermes package-manager cache.
- Use a long random ntfy topic. Anyone who knows it can send control messages.
- The Pinggy TCP endpoint is reachable over the internet. Use a strong unique SSH password and rotate credentials if they are ever exposed.
- The SSH configuration disables root login, public-key login, X11 forwarding, agent forwarding, and SSH TCP forwarding.

## Repository files

- `.github/workflows/sandbox.yml`: one START / STOP workflow.
- `kernel/kernel-metadata.json`: fixed Kaggle kernel metadata and dataset attachments.
- `kernel/main.py`: direct Dataset secret/config loading, offline runtime restore/export, SSH setup, Hermes installation, Pinggy tunnel, and ntfy STOP polling.

# Hermes Kaggle Sandbox (iPhone + Termius + Pinggy Pro)

One fixed Kaggle script kernel is controlled by one GitHub Actions workflow with `SETUP_DATASETS`, `START`, and `STOP`. The setup action creates the three private Kaggle Datasets automatically; no empty Dataset needs to be created by hand.

- GitHub repository: `subelips/sandbox`
- Kernel: `maithanhtu/sandbox`
- Datasets:
  - `maithanhtu/sandbox-package-cache`
  - `maithanhtu/sandbox-secret-store`
  - `maithanhtu/sandbox-runtime`
- Pinggy hostname: `sandboxx.a.pinggy.link`
- Reserved Pinggy remote port: `19326`
- SSH username: `sandbox`

## 1. One-time GitHub Actions setup

In GitHub, open **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `KAGGLE_USERNAME` | `maithanhtu` |
| `KAGGLE_KEY` | Your current Kaggle API key |
| `NTFY_TOPIC` | A long random private topic; use the exact same value in the secret Dataset |

The Kaggle API key must be generated in your Kaggle account and stored only as a GitHub Actions Secret. Never commit it to this repository or send it in chat.

## 2. Automatically create all three Datasets

1. Open **Actions → Kaggle Sandbox → Run workflow**.
2. Select **SETUP_DATASETS**.
3. Run the workflow and wait for all three Dataset status checks to succeed.

Kaggle Datasets are private by default when created through the CLI. The workflow intentionally does not pass `--public`. It creates or versions these Dataset IDs:

| Dataset | Purpose |
|---|---|
| `maithanhtu/sandbox-package-cache` | Offline `.pkg`, `.deb`, wheels and other package archives |
| `maithanhtu/sandbox-secret-store` | `secrets.json`, Hermes `config.yaml`, and `.env` |
| `maithanhtu/sandbox-runtime` | Complete Hermes source/runtime archive |

The tiny README/example files in the repository are seed files. They satisfy Kaggle's requirement that a Dataset upload contain at least one file; they are not the actual secrets or runtime payload.

## 3. Add the real secret configuration directly to the Secret Dataset

Open the newly created private Dataset `sandbox-secret-store` on Kaggle and upload a file named `secrets.json` at its root. Use this structure, replacing the placeholders on your iPhone:

```json
{
  "PINGGY_TOKEN": "YOUR_CURRENT_PINGGY_TOKEN",
  "SSH_PASSWORD": "A_LONG_UNIQUE_PASSWORD",
  "NTFY_TOPIC": "THE_SAME_RANDOM_TOPIC_AS_GITHUB_ACTIONS",
  "PINGGY_HOST": "sandboxx.a.pinggy.link",
  "PINGGY_REMOTE_PORT": "19326",
  "PINGGY_GATEWAY": "pro.pinggy.io"
}
```

Also create a folder named `hermes-config` in that Dataset and put your personal Hermes `config.yaml` and `.env` inside it:

```text
sandbox-secret-store/
  secrets.json
  hermes-config/
    config.yaml
    .env
```

The Notebook reads these files directly from the mounted private Dataset. It does **not** use Kaggle Secrets. Never upload real credentials to this GitHub repository. Private does not mean encrypted: anyone with access to the Dataset or running kernel may be able to access its contents.

## 4. Runtime and package cache

### Runtime Dataset

The `sandbox-runtime` Dataset is strictly the offline Hermes installation bundle, not chat history or personal configuration. Its expected payload is:

```text
hermes-runtime.tar.gz
```

For the first build, the Notebook installs Hermes from the official installer. On cooperative STOP it exports the runtime bundle to Kaggle kernel output at:

```text
/kaggle/working/hermes-runtime-export/hermes-runtime.tar.gz
```

After the first successful build, download that output from the Kaggle kernel page and upload it as a new version of `sandbox-runtime`. Subsequent starts restore the bundle instead of repeating the main Hermes installation. This initial runtime publication is still a manual step; the workflow currently automates Dataset creation, not the transfer of a kernel output archive back into the Dataset.

The archive currently includes `~/.local`, `~/.cache`, and `~/.hermes/hermes-agent`; it excludes personal config and credentials. It is tied to the Kaggle Linux architecture and compatible system libraries. Optional integrations may still download their own components on first use.

### Package Cache Dataset

The package-cache Dataset is created and attached automatically, but its `.pkg` / `.deb` / wheel formats are not yet wired into every system and Hermes package-manager install path. Do not assume a completely air-gapped boot until that integration and the required OS dependency closure have been tested.

## 5. Start and connect from iPhone

Before START, confirm that:
- all three Dataset attachments exist;
- `sandbox-secret-store` contains your real `secrets.json`;
- `hermes-config/config.yaml` and `.env` are present if required;
- Pinggy dashboard confirms the reserved hostname, TCP port, gateway and remote-forward syntax.

Then:

1. Open **Actions → Kaggle Sandbox → Run workflow**.
2. Select **START**.
3. Wait for the Kaggle kernel to install/restore Hermes and establish the Pinggy tunnel.
4. In Termius, create an SSH connection:
   - Host: `sandboxx.a.pinggy.link`
   - Port: `19326`
   - Username: `sandbox`
   - Password: the `SSH_PASSWORD` value in the Secret Dataset
5. Run:

```bash
export PATH="$HOME/.local/bin:$PATH"
hermes model
```

To stop, run the same workflow and select **STOP**. The kernel polls the private ntfy topic and exits cooperatively after receiving the STOP message.

## 6. Current automation boundaries

Automated now:
- Create or version all three private Kaggle Datasets.
- Check that the three Dataset IDs exist before START.
- Push the fixed Kaggle kernel for START.
- Send the cooperative STOP signal.

Still requires one-time/manual user action:
- Add real credentials and Hermes config to the private Secret Dataset. They are intentionally not committed to GitHub.
- Publish the first `hermes-runtime.tar.gz` from the first successful Kaggle run.
- Confirm Pinggy's actual gateway and forwarding syntax in your account dashboard.

Kaggle is an ephemeral runtime, not a guaranteed 24/7 VPS. Kaggle may stop sessions due to runtime limits, quotas, inactivity or platform policy. Abrupt termination can prevent the runtime archive from being exported. The first install still needs internet; the package cache is not yet a complete offline installer.

## Repository structure

- `.github/workflows/sandbox.yml`: Dataset setup plus START / STOP workflow.
- `datasets/*/dataset-metadata.json`: Kaggle Dataset metadata.
- `datasets/*/README.md`: tiny seed files for Dataset creation.
- `kernel/kernel-metadata.json`: fixed kernel metadata and three Dataset attachments.
- `kernel/main.py`: direct Dataset secret/config loading, runtime restore/export, SSH, Hermes install, Pinggy tunnel and STOP polling.

# Kaggle Sandbox — iPhone + Termius + Pinggy

This repository contains the deployment controller and Kaggle notebook files for a disposable sandbox.

## Security

Never commit Kaggle API keys, Pinggy tokens, SSH passwords, ntfy topics, Hermes `.env`, or personal configuration. Store credentials in GitHub Actions Secrets and Kaggle Secrets only.

## Status

Deployment files are being prepared. Kaggle runtimes are ephemeral and are not a 24/7 VPS. The START/STOP workflow uses a cooperative STOP signal delivered through a private ntfy topic.

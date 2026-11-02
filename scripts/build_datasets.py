#!/usr/bin/env python3
"""Rebuild the `hermes-agent-pkg` dataset from the official installer.

Pipeline (all through the public Kaggle API):

  1. push  kernel/builder.ipynb  -> runs install.sh on Kaggle's own image
  2. wait  for the run to finish
  3. pull  /kaggle/working/hermes-agent-full.pkg + manifest.json
  4. create or version  dataset maithanhtu/hermes-agent-pkg

Why on Kaggle and not locally: the .pkg must match the runtime exactly
(same Ubuntu, same Python minor, same glibc). Building it on a Kaggle kernel
makes the extract on boot a plain `tar`, with nothing to compile or resolve.

Usage:  KAGGLE_API_TOKEN=... python scripts/build_datasets.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

USER = "maithanhtu"
KERNEL = f"{USER}/hermes-builder"
DATASET = f"{USER}/hermes-agent-pkg"
ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = pathlib.Path("/tmp/kbuild-work")


def run(cmd, **kw):
    print(f"$ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, check=True, text=True, **kw)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    stage = WORK / "kernel"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for f in ("builder.ipynb", "kernel-metadata.json"):
        shutil.copy(ROOT / "scripts" / "builder_assets" / f, stage / f)

    run(f"python3 -m kaggle kernels push -p {stage}")

    for i in range(180):
        out = subprocess.run(f"python3 -m kaggle kernels status {KERNEL}",
                             shell=True, capture_output=True, text=True).stdout
        print(f"  [{i}] {out.strip()}", flush=True)
        if "COMPLETE" in out or "ERROR" in out:
            break
        time.sleep(20)
    else:
        print("builder did not finish in time", file=sys.stderr)
        return 1

    out_dir = WORK / "out"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    run(f"python3 -m kaggle kernels output {KERNEL} -p {out_dir}")

    ds = WORK / "dataset"
    if ds.exists():
        shutil.rmtree(ds)
    ds.mkdir(parents=True)
    shutil.copy(out_dir / "hermes-agent-full.pkg", ds / "hermes-agent-full.pkg")
    shutil.copy(out_dir / "manifest.json", ds / "manifest.json")
    (ds / "dataset-metadata.json").write_text(json.dumps({
        "title": "hermes agent pkg", "id": DATASET,
        "licenses": [{"name": "CC0-1.0"}]}, indent=1) + "\n")

    size = (ds / "hermes-agent-full.pkg").stat().st_size
    print(f"pkg = {size/1e6:.0f} MB")

    exists = subprocess.run(
        f"python3 -m kaggle datasets view {DATASET}", shell=True,
        capture_output=True, text=True).returncode == 0
    if exists:
        run(f"python3 -m kaggle datasets version -p {ds} -m 'hermes pkg {time.strftime('%Y-%m-%d %H:%M')}' -r zip")
    else:
        run(f"python3 -m kaggle datasets create -p {ds} -r zip")
    print("done:", DATASET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

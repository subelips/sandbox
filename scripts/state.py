#!/usr/bin/env python3
"""Read / write state.json atomically. One control plane for the whole sandbox."""
import json
import pathlib
import sys
import time

PATH = pathlib.Path(__file__).resolve().parent.parent / "state.json"


def load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except Exception:
        return {"mode": "off", "seq": 0}


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"
    data = load()
    if cmd == "get":
        print(data.get("mode", "off"))
        return 0
    if cmd == "json":
        print(json.dumps(data, ensure_ascii=False))
        return 0
    if cmd == "set":
        data["mode"] = sys.argv[2]
        data["seq"] = int(data.get("seq", 0)) + 1
        data["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["by"] = sys.argv[3] if len(sys.argv) > 3 else "github-actions"
        PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(data["mode"])
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

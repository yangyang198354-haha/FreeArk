"""Read-only Codex app-server config/hooks probe. Does not trust or run hooks.

No model turn is started. Only sanitized hook/config metadata is saved.
"""
import argparse
import json
from pathlib import Path
import queue
import shutil
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[2]


def executable():
    command = shutil.which("codex.exe")
    if command:
        return command
    command = shutil.which("codex.cmd") or shutil.which("codex")
    if not command:
        raise RuntimeError("Codex CLI not on PATH")
    package = Path(command).parent / "node_modules/@openai"
    matches = list(package.glob("codex*/**/codex.exe"))
    if matches:
        return str(matches[0])
    return command


def probe():
    proc = subprocess.Popen([executable(), "app-server", "--stdio"], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    messages = queue.Queue()

    def read():
        for line in proc.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=read, daemon=True).start()

    def request(number, method, params):
        proc.stdin.write(json.dumps({"id": number, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        while True:
            row = messages.get(timeout=30)
            if row.get("id") == number:
                if "error" in row:
                    raise RuntimeError(f"{method}: {row['error']}")
                return row["result"]
    try:
        init = request(1, "initialize", {"clientInfo": {"name": "sdlc_migration_probe", "version": "1.0"},
                                         "capabilities": {"experimentalApi": True}})
        proc.stdin.write('{"method":"initialized"}\n')
        proc.stdin.flush()
        config = request(2, "config/read", {"cwd": str(ROOT), "includeLayers": True})
        hooks = request(3, "hooks/list", {"cwds": [str(ROOT)]})
        entries = []
        for entry in hooks.get("data", []):
            local = [row for row in entry.get("hooks", []) if str(ROOT).lower().replace("\\", "/") in str(row.get("sourcePath", "")).lower().replace("\\", "/")]
            entries.append({"cwd": entry.get("cwd"), "errors": entry.get("errors"), "warnings": entry.get("warnings"),
                            "hooks": [{key: row.get(key) for key in ("eventName", "sourcePath", "command", "trustStatus", "enabled", "matcher")} for row in local]})
        # Never serialize full config: it may contain credentials or private MCP endpoints.
        result = {"server": init.get("userAgent"), "features_hooks": config.get("config", {}).get("features", {}).get("hooks"),
                  "layers": [{"name": row.get("name"), "disabledReason": row.get("disabledReason")} for row in config.get("layers", [])],
                  "project_hooks": entries, "model_turn_started": False, "trust_modified": False}
        return result
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/codex-runtime-probe.json")
    args = parser.parse_args()
    result = probe()
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))

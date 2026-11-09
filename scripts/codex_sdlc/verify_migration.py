"""Verify installed source coverage, prompt structure, skills, and native exec rules."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib

import migrate
from probe_runtime import executable

ROOT = Path(__file__).resolve().parents[2]
# Created per target repo at first run (PM bootstrap / memory seeding); absence is not a broken reference.
OPTIONAL_REFERENCES = (re.compile(r"^\.codex/sdlc/project_profile\.md$"), re.compile(r"^\.codex/agent-memory/"),
                       re.compile(r"^\.agents/skills/"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="print only; do not write output/codex-migration-verification.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / ".codex/sdlc/migration_manifest.json").read_text(encoding="utf-8"))
    errors = []
    for row in manifest["files"]:
        if migrate.sha(ROOT / row["target"]) != row["sha256"]:
            errors.append("Installed hash mismatch: " + row["target"])
        if row["source"] and migrate.sha(ROOT / row["source"]) != row["source_sha256"]:
            errors.append("Source changed: " + row["source"])
    roles = {}
    for role in manifest["roles"]:
        config = tomllib.loads((ROOT / f".codex/agents/{role}.toml").read_text(encoding="utf-8"))
        source = (ROOT / f".claude/agents/{role}.md").read_text(encoding="utf-8")
        _, source_body = migrate.frontmatter(source)
        target_body = config["developer_instructions"]
        if config["name"] != role or not config["description"]:
            errors.append("Role identity invalid: " + role)
        if set(config) - {"name", "description", "developer_instructions", "features"}:
            errors.append("Unexpected native fields: " + role)
        # Every numbered source section must remain; platform wording may differ.
        headings = re.findall(r"^## (\d+)\.", source_body, re.M)
        target_headings = re.findall(r"^## (\d+)\.", target_body, re.M)
        if headings != target_headings:
            errors.append("Source section loss: " + role)
        if role != "pm-orchestrator" and "<agent_response>" not in target_body:
            errors.append("Structured response missing: " + role)
        if ".claude/" in target_body or "subagent_type" in target_body:
            errors.append("Stale runtime reference: " + role)
        for path in re.findall(r"`(\.(?:codex|agents)/[^`]+)`", target_body):
            if any(char in path for char in "{}*|\n") or path.endswith("/"):
                continue
            if not (ROOT / path).exists() and not any(p.search(path) for p in OPTIONAL_REFERENCES):
                errors.append(f"Broken reference ({role}): {path}")
        roles[role] = {"sections": len(headings), "source_lines": len(source_body.splitlines()), "target_lines": len(target_body.splitlines())}
    pm_toml = tomllib.loads((ROOT / ".codex/agents/pm-orchestrator.toml").read_text(encoding="utf-8"))["developer_instructions"]
    pm_md = (ROOT / ".codex/sdlc/pm-orchestrator.md").read_text(encoding="utf-8")
    if pm_toml.rstrip() != pm_md.rstrip():
        errors.append("PM definitions drifted: .codex/agents/pm-orchestrator.toml vs .codex/sdlc/pm-orchestrator.md (rerun migrate.py)")
    rules = []
    settings = json.loads((ROOT / migrate.settings_source()).read_text(encoding="utf-8"))
    try:
        command = executable()
    except RuntimeError:
        command = None
        rules = "SKIPPED: codex CLI not on PATH; native execpolicy checks not run"
    for action, expected in [("ask", "prompt"), ("deny", "forbidden")]:
        if command is None:
            break
        for spec in settings["permissions"].get(action, []):
            words = spec.removeprefix("Bash(").removesuffix(")").replace("*", "").split()
            process = subprocess.run([command, "execpolicy", "check", "--rules", str(ROOT / ".codex/rules/sdlc.rules"), "--", *words],
                                     capture_output=True, text=True, encoding="utf-8", timeout=15)
            if process.returncode:
                errors.append("Native rule parser failed: " + spec)
                continue
            decision = json.loads(process.stdout).get("decision")
            rules.append({"source": spec, "expected": expected, "actual": decision})
            if decision != expected:
                errors.append("Rule regression: " + spec)
    result = {"source_version": manifest["source_version"], "source_commit": manifest["source_commit"],
              "files_verified": len(manifest["files"]), "roles": roles, "native_rule_checks": rules,
              "errors": errors, "passed": not errors,
              "note": "Static/source and native rule validation only. Does not prove hook trust or end-to-end runtime enforcement."}
    if not args.no_write:
        path = ROOT / "output/codex-migration-verification.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(manifest["files"]), "roles": len(roles),
                      "rules": rules if isinstance(rules, str) else len(rules), "passed": not errors, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

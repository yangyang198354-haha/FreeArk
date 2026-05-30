#!/bin/bash
# Probe runner for openclaw_schema_probes.md §6
# Run via: bash scripts/run_probes.sh

SSH_CMD="ssh -o BatchMode=yes -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -i /c/fa-home/.ssh/id_ed25519 -p 57279 -o ConnectTimeout=20 \
  yangyang@et116374mm892.vicp.fun"

echo "=== PROBE-A: openclaw config schema ==="
$SSH_CMD 'openclaw config schema | python3 -m json.tool 2>&1'
echo ""

echo "=== PROBE-B: openclaw skills list ==="
$SSH_CMD 'openclaw skills list 2>&1'
echo ""

echo "=== PROBE-C: openclaw skills check ==="
$SSH_CMD 'openclaw skills check 2>&1'
echo ""

echo "=== PROBE-D: healthcheck SKILL.md ==="
$SSH_CMD 'cat /usr/lib/node_modules/openclaw/skills/healthcheck/SKILL.md 2>&1'
echo ""

echo "=== PROBE-E: diagram-maker SKILL.md ==="
$SSH_CMD 'cat /usr/lib/node_modules/openclaw/skills/diagram-maker/SKILL.md 2>&1'
echo ""

echo "=== PROBE-F: taskflow SKILL.md ==="
$SSH_CMD 'cat /usr/lib/node_modules/openclaw/skills/taskflow/SKILL.md 2>&1'
echo ""

echo "=== PROBE-G: taskflow directory listing ==="
$SSH_CMD 'ls -la /usr/lib/node_modules/openclaw/skills/taskflow/ 2>&1'
echo ""

echo "=== PROBE-H: openclaw skills info healthcheck ==="
$SSH_CMD 'openclaw skills info healthcheck 2>&1'
echo ""

echo "=== PROBE-I: current openclaw.json ==="
$SSH_CMD 'cat ~/.openclaw/openclaw.json | python3 -m json.tool 2>&1'
echo ""

echo "=== PROBES COMPLETE ==="

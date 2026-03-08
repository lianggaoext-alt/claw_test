#!/usr/bin/env bash
set -euo pipefail

# Guard rule:
# Block wecom-* jobs if they use announce delivery without explicit target.

json="$(openclaw cron list --json 2>/dev/null || true)"
if [ -z "$json" ]; then
  echo "cron_guard: unable to fetch cron list"
  exit 0
fi

# Use python for robust JSON handling on old systems.
python3 - <<'PY'
import json, subprocess, sys

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

code, out, err = run(["openclaw", "cron", "list", "--json"])
if code != 0:
    print("cron_guard: list failed", err)
    sys.exit(0)

try:
    jobs = json.loads(out)
except Exception:
    print("cron_guard: invalid json")
    sys.exit(0)

if isinstance(jobs, dict):
    jobs = jobs.get("jobs", [])

blocked = 0
for j in jobs or []:
    agent_id = str(j.get("agentId", ""))
    if not agent_id.startswith("wecom-"):
        continue
    delivery = j.get("delivery", {}) or {}
    mode = str(delivery.get("mode", ""))
    to = str(delivery.get("to", "")).strip()
    if mode == "announce" and not to:
        job_id = j.get("id") or j.get("jobId")
        if not job_id:
            continue
        # disable risky job
        rc, so, se = run(["openclaw", "cron", "disable", str(job_id)])
        if rc == 0:
            blocked += 1
            print(f"cron_guard: disabled invalid wecom job {job_id}")
        else:
            print(f"cron_guard: failed to disable {job_id}: {se}")

print(f"cron_guard: done, blocked={blocked}")
PY

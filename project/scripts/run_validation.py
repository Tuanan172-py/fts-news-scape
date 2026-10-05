# -*- coding: utf-8 -*-
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.process_l1_pipeline import build_l1_output, check_l1_dod

total = 0
passed = 0
failed = 0
recognized = 0
unrecognized_list = []

for b in range(1, 17):
    p = PROJECT_ROOT / f"data/agent_tasks/l1/l1_batch_{b:02d}.task.json"
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    for t in data["tasks"]:
        total += 1
        out = build_l1_output(t)
        ok, reasons = check_l1_dod(out, t["title"])
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"FAIL [Batch {b:02d}] {t['title']}")
            print(f"  reasons: {reasons}")
        if out["recognized"]:
            recognized += 1
        else:
            unrecognized_list.append((b, t["title"]))

print(f"Total: {total}, Passed DoD: {passed}, Failed DoD: {failed}, Recognized: {recognized}, Unrecognized: {len(unrecognized_list)}")
if unrecognized_list:
    print("\n--- Unrecognized titles sample (first 10) ---")
    for b, title in unrecognized_list[:10]:
        print(f"[{b:02d}] {title}")

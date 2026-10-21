"""Reduce the backlog wave manifest to the repair batches whose id ends with `_r01`."""
import json
from pathlib import Path

manifest_path = Path(r"C:\data\news-scape\agent_tasks\article\wave_W1012_BACKLOG500.json")
data = json.loads(manifest_path.read_text(encoding="utf-8"))

# Keep only the _r01 repair batches so agy_runner runs just those 9 repair batches.
repair_batches = []
for b in data.get("batches", []):
    bid = b.get("batch_id", "")
    if bid.endswith("_r01"):
        repair_batches.append({
            "batch_id": bid,
            "path": rf"C:\data\news-scape\agent_tasks\article\{bid}.task.json",
            "task_file": rf"agent_tasks\article\{bid}.task.json"
        })

data["batches"] = repair_batches
manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"Da thiet lap manifest chi gom {len(repair_batches)} lo repair _r01!")

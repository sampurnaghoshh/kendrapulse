"""Write the static demo snapshot the frontend loads when the API is unreachable.

    cd backend && .venv/Scripts/python.exe scripts/export_snapshot.py

Everything is built by `demo/snapshot.py`; this file only writes it and reports the size, so
the snapshot and a live API response can never be two different stories.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.snapshot import SNAPSHOT_PATH, build_snapshot  # noqa: E402


def main():
    started = time.perf_counter()
    snapshot = build_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Compact separators: the file is fetched by a browser, not read by a person.
    text = json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)
    SNAPSHOT_PATH.write_text(text, encoding="utf-8")
    json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))  # it must read back

    size = SNAPSHOT_PATH.stat().st_size
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"size {size:,} bytes ({size / 1024:.1f} KB)")
    print(f"counterfactual worlds {len(snapshot['counterfactual_worlds'])}, "
          f"fix replays {len(snapshot['fix_replays'])}, "
          f"validation {'included' if snapshot['validation'] else 'missing'}")
    print(f"commit {snapshot['meta']['git_commit'][:12]}, built in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

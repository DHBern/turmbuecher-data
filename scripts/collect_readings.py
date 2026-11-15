"""Take a gateway run's readings into ``readings/<reader>.jsonl``.

    python scripts/collect_readings.py <run directory> [<run directory> ...]

A run directory is an atr-batch run copied from tei
(``vlm_test/<run>/<model>/<page key>.json``, each with ``text`` and
``truncated``). One line per page is written, ``{"key", "text"}`` (plus
``truncated``); pages a reader already has are replaced, none is removed.
Only pages named in ``readings/pages.tsv`` are taken.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"transkribus-bestand", "joint"}


def main() -> None:
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        known = {r["key"] for r in csv.DictReader(fh, delimiter="\t")}
    for run in map(Path, sys.argv[1:]):
        for folder in sorted(p for p in run.iterdir() if p.is_dir() and p.name not in SKIP):
            out = ROOT / "readings" / f"{folder.name}.jsonl"
            have = {}
            for line in out.read_text(encoding="utf-8").splitlines() if out.exists() else []:
                r = json.loads(line)
                have[r["key"]] = r
            new = 0
            for f in sorted(folder.glob("*.json")):
                if f.stem not in known:
                    continue
                d = json.loads(f.read_text(encoding="utf-8"))
                rec = {"key": f.stem, "text": (d.get("text") or "").strip("\n")}
                if d.get("truncated"):
                    rec["truncated"] = True
                new += f.stem not in have
                have[f.stem] = rec
            tmp = out.with_suffix(".part")
            tmp.write_text("".join(json.dumps(have[k], ensure_ascii=False) + "\n" for k in sorted(have)), encoding="utf-8")
            tmp.replace(out)
            cut = sum(1 for r in have.values() if r.get("truncated"))
            empty = sum(1 for r in have.values() if not r["text"].strip())
            print(f"{folder.name}: {len(have)} pages ({new} new), {cut} truncated, {empty} empty")


if __name__ == "__main__":
    main()

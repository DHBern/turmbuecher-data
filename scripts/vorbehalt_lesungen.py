"""Readings of models trained on the withheld Ground Truth, taken off the Ground-Truth pages.

    python scripts/vorbehalt_lesungen.py

TrOCR Turmbücher (``trocr-towerbooks-tklines``) was fine-tuned on the Ground Truth
of these volumes. On those pages it gives the Ground Truth back almost word for
word (measured 17.11.2026 on 100 hand-corrected pages: median CER 0.1 %), so its
reading there would publish the Ground Truth before 1 July 2027 under another
name. Its text is removed from every page that ``readings/vorbehalt.tsv`` marks as
Ground Truth; the page stays in the file with ``"vorbehalt": true`` and no text.
Run after ``collect_readings.py`` and before ``joint_reading.py``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINED_ON_GT = ["trocr-towerbooks-tklines"]


def main() -> None:
    with (ROOT / "readings" / "vorbehalt.tsv").open(encoding="utf-8") as fh:
        gt = {r["key"] for r in csv.DictReader(fh, delimiter="\t") if r["ground_truth"]}
    for reader in TRAINED_ON_GT:
        path = ROOT / "readings" / f"{reader}.jsonl"
        recs, n = [], 0
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["key"] in gt and (r.get("text") or "").strip():
                r = {"key": r["key"], "text": "", "vorbehalt": True}
                n += 1
            recs.append(r)
        tmp = path.with_suffix(".part")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        tmp.replace(path)
        print(f"{reader}: text removed on {n} Ground-Truth pages")


if __name__ == "__main__":
    main()

"""Take readings from elsewhere into ``readings/<reader>.jsonl``.

    python scripts/collect_readings.py <run directory> [...]              # gateway runs
    python scripts/collect_readings.py --jsonl <dir> [...] [--pagexml DIR] # UBELIX shards

A gateway run directory (``vlm_test/<run>/<model>/<page key>.json``, copied
from tei) holds one file per page with ``text`` and ``truncated``.

A UBELIX directory (``turmbuecher-readings/ubelix/<reader>/shard-*.jsonl``)
holds one line per page: page readers write ``{"key", "text", "truncated"}``,
line readers (TrOCR on the Transkribus lines, ubelix/read_lines.py) write
``{"key", "lines": [{"id", "text"}]}``. A line reader's page text is put in the
reading order of the PAGE XML (``--pagexml``, the local copy of the ingest), and
where Transkribus has text on the page, only its lines with text are kept: then
line *i* of the reading is line *i* of the Transkribus text, and both link to
the same row on the image.

One line per page is written, ``{"key", "text"}`` (plus ``truncated``); pages a
reader already has are replaced, none is removed. Only pages named in
``readings/pages.tsv`` are taken.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SKIP = {"transkribus-bestand", "joint"}


def load(out: Path) -> dict[str, dict]:
    have = {}
    for line in out.read_text(encoding="utf-8").splitlines() if out.exists() else []:
        r = json.loads(line)
        have[r["key"]] = r
    return have


def save(out: Path, have: dict[str, dict], new: int, name: str) -> None:
    tmp = out.with_suffix(".part")
    tmp.write_text("".join(json.dumps(have[k], ensure_ascii=False) + "\n" for k in sorted(have)), encoding="utf-8")
    tmp.replace(out)
    cut = sum(1 for r in have.values() if r.get("truncated"))
    empty = sum(1 for r in have.values() if not r["text"].strip())
    print(f"{name}: {len(have)} pages ({new} new), {cut} truncated, {empty} empty")


def from_runs(runs: list[Path], known: set[str]) -> None:
    for run in runs:
        for folder in sorted(p for p in run.iterdir() if p.is_dir() and p.name not in SKIP):
            out = ROOT / "readings" / f"{folder.name}.jsonl"
            have, new = load(out), 0
            for f in sorted(folder.glob("*.json")):
                if f.stem not in known:
                    continue
                d = json.loads(f.read_text(encoding="utf-8"))
                rec = {"key": f.stem, "text": (d.get("text") or "").strip("\n")}
                if d.get("truncated"):
                    rec["truncated"] = True
                new += f.stem not in have
                have[f.stem] = rec
            save(out, have, new, folder.name)


def from_jsonl(dirs: list[Path], known: set[str], pagexml: Path | None) -> None:
    import import_transkribus as it
    for folder in dirs:
        out = ROOT / "readings" / f"{folder.name}.jsonl"
        have, new, unordered = load(out), 0, 0
        for f in sorted(folder.glob("shard-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue            # a shard may be writing its last line right now
                if r.get("key") not in known:
                    continue
                if "lines" in r:
                    by_id = {x["id"]: x["text"] for x in r["lines"]}
                    order = None
                    if pagexml and (pagexml / f"{r['key']}.xml").exists():
                        lines, _ = it.read_page(pagexml / f"{r['key']}.xml")
                        with_text = [x for x in lines if x["text"].strip()]
                        order = [x["id"] for x in (with_text or lines)]
                    if order is None:
                        unordered += 1
                        order = [x["id"] for x in r["lines"]]
                    text = "\n".join(by_id.get(i, "") for i in order)
                    rec = {"key": r["key"], "text": text}
                else:
                    rec = {"key": r["key"], "text": (r.get("text") or "").strip("\n")}
                    if r.get("truncated"):
                        rec["truncated"] = True
                new += r["key"] not in have
                have[r["key"]] = rec
        save(out, have, new, folder.name)
        if unordered:
            print(f"  {unordered} pages of {folder.name} without PAGE XML here: lines in the reader's order")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--jsonl", action="store_true", help="the directories hold UBELIX shards")
    ap.add_argument("--pagexml", type=Path, default=ROOT / "_ingest" / "pagexml")
    args = ap.parse_args()
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        known = {r["key"] for r in csv.DictReader(fh, delimiter="\t")}
    if args.jsonl:
        from_jsonl(args.dirs, known, args.pagexml if args.pagexml.exists() else None)
    else:
        from_runs(args.dirs, known)


if __name__ == "__main__":
    main()

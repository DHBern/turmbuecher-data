"""The joint reading: the independent readings of a page combined into one.

    python scripts/joint_reading.py [--readers a,b,c]

No reading is measured against ground truth here (that is not this project's
aim), so no reader gets a learned weight. The rule is plain and can be checked
by eye in the viewer:

* The **backbone** of a page is the text that stands in Transkribus
  (``transkribus-bestand``): it carries the line breaks the image is linked to.
  Where a page has no such text, the backbone is the first reader in
  ``--readers`` that has read the page.
* A page Transkribus marks as ground truth (GT, DONE, FINAL) is taken over
  unchanged.
* Elsewhere a word of the backbone is replaced only where **at least two other
  readers agree on the same different word** at that place. Only one-to-one
  word substitutions are voted on; insertions, deletions and line breaks stay
  as the backbone has them. One other reader alone never changes anything.

Only pages where something was combined are written (two or more other
readers, or no Transkribus text): elsewhere the joint reading would be the
Transkribus text under another name.

Writes ``readings/joint.jsonl``: ``key``, ``text``, ``backbone``, ``readers``
(who else had read the page) and ``changes`` (line, from, to, by).
The method is the St. Gallen Missives' weighted backbone
(DHBern/sg-missiven-data, scripts/joint_reading.py) with equal weights.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKBONE = "transkribus-bestand"
DEFAULT_READERS = ["qwen3.5-4b-german-kurrent-xvi-xix-page-v1", "trocr-kurrent-xvi-xvii"]
CORRECTED = {"GT", "DONE", "FINAL"}
TOKEN = re.compile(r"\S+")


def load(reader: str) -> dict[str, str]:
    path = ROOT / "readings" / f"{reader}.jsonl"
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        r = json.loads(line)
        text = "\n".join(x.rstrip() for x in (r.get("text") or "").splitlines() if x.strip())
        if text:
            out[r["key"]] = text
    return out


def norm_tok(t: str) -> str:
    return re.sub(r"[^\w]", "", t.lower())


def combine(backbone: str, others: dict[str, str], need: int = 2) -> tuple[str, list[dict]]:
    """The backbone with every word replaced that ``need`` other readers agree
    to read differently, and the list of those changes."""
    lines = backbone.split("\n")
    btoks = [(li, m) for li, line in enumerate(lines) for m in TOKEN.finditer(line)]
    bnorm = [norm_tok(m.group()) for _, m in btoks]
    votes: list[dict[str, list[str]]] = [defaultdict(list) for _ in btoks]
    for reader, text in others.items():
        otoks = TOKEN.findall(text)
        onorm = [norm_tok(t) for t in otoks]
        sm = difflib.SequenceMatcher(None, bnorm, onorm, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
                for k in range(i2 - i1):
                    votes[i1 + k][otoks[j1 + k]].append(reader)
    changes, new_tokens = [], []
    for idx, (li, m) in enumerate(btoks):
        mine = m.group()
        by_norm: dict[str, set[str]] = defaultdict(set)
        forms: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for tok, readers in votes[idx].items():
            n = norm_tok(tok)
            by_norm[n].update(readers)
            forms[n][tok] += len(readers)
        best = max(by_norm, key=lambda n: len(by_norm[n]), default="")
        if best and best != norm_tok(mine) and len(by_norm[best]) >= need:
            pick = max(forms[best], key=forms[best].get)
            lead, trail = re.match(r"^\W*", mine).group(), re.search(r"\W*$", mine).group()
            new = lead + (re.sub(r"^\W+|\W+$", "", pick) or pick) + trail
            changes.append({"line": li, "from": mine, "to": new, "by": sorted(by_norm[best])})
            new_tokens.append((li, m, new))
        else:
            new_tokens.append((li, m, mine))
    out_lines = []
    for li, line in enumerate(lines):
        pieces, pos = [], 0
        for l2, m, new in new_tokens:
            if l2 == li:
                pieces += [line[pos:m.start()], new]
                pos = m.end()
        pieces.append(line[pos:])
        out_lines.append("".join(pieces))
    return "\n".join(out_lines), changes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--readers", default=",".join(DEFAULT_READERS))
    args = ap.parse_args()
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        pages = list(csv.DictReader(fh, delimiter="\t"))
    back = load(BACKBONE)
    readers = {r: load(r) for r in args.readers.split(",") if r}
    readers = {r: p for r, p in readers.items() if p}
    print(f"voting readers: {', '.join(f'{r} ({len(p)} pages)' for r, p in readers.items()) or 'none'}")
    out, stats = [], defaultdict(int)
    for p in pages:
        key = p["key"]
        have = {r: pg[key] for r, pg in readers.items() if key in pg}
        if key in back:
            bb, text = BACKBONE, back[key]
        elif have:
            bb = next(iter(have))
            text = have.pop(bb)
        else:
            continue
        if p["status"] in CORRECTED and bb == BACKBONE:
            joint, changes = text, []
            stats["taken over (ground truth)"] += 1
        elif len(have) >= 2:
            joint, changes = combine(text, have)
            stats["voted"] += 1
        else:
            joint, changes = text, []
            stats["backbone alone (fewer than two other readers)"] += 1
        if bb == BACKBONE and len(have) < 2:
            continue        # nothing was combined: the page has its Transkribus text, shown as such
        stats["words changed"] += len(changes)
        if bb != BACKBONE:
            stats["without Transkribus text"] += 1
        out.append({"key": key, "text": joint, "backbone": bb, "readers": sorted(have), "changes": changes})
    path = ROOT / "readings" / "joint.jsonl"
    tmp = path.with_suffix(".part")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    tmp.replace(path)
    print(f"{len(out)} pages; " + "; ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()

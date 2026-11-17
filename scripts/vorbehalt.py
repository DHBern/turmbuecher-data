"""Which Transkribus text may be published now, and the list of Ground Truth.

    python scripts/vorbehalt.py [--src _ingest/vorbehalt]

Decision of 17.11.2026 (Tobias Hodel): until the Ground Truth is published on
1 July 2027, only **machine readings** are published. A page's Transkribus text
counts as a machine reading when it is the output of a recognition model,
unchanged — the same characters as the newest HTR version of that page in the
older collections the documents were copied from (89729 «StABE_Turmbücher_DH»,
63705 «StABE_Turmbücher»). Tags added later (persons, places, dates) do not
change the text and stay.

A text whose latest version in 187323 is itself a recognition run (Flow re-ran
newer models there) is a machine reading as it stands.

Per page of collection 187323 (by its image, ``tk``):

* **ground truth** — the page is marked GT (or DONE/FINAL) in any of the four
  collections, in any transcript version, or in a training/validation set
  (215878 «StABE_Turmbücher_DH_flow_GT», the TRAINING_VALIDATION_SET documents).
  Its Transkribus text is withheld; the newest HTR version is shown instead, if
  there is one.
* **von Hand** — not marked GT, but the text differs from every HTR output (or
  none exists): corrected or typed by hand. Same treatment.
* **andere Sammlung** — the page is empty in 187323 but has a machine reading
  in 89729 or 63705 (B IX 424, 474, 484, 505 …): that reading is taken over.

Inputs in ``--src`` (fetched on tei, not committed; no user names in them):
``survey_cols.jsonl`` (every page of the four collections: status, ``any_gt``,
image ``tk``), ``htr_versions/index.jsonl``, ``htr_versions/htr/<col>_<tk>.xml``
(the newest HTR version), ``htr_versions/latest/<col>_<tk>.xml`` (latest version
of pages empty in 187323).

Writes ``readings/vorbehalt.tsv`` (key, ground_truth, text, quelle), the PAGE XML
to publish instead in ``_ingest/pagexml_public/<key>.xml``, and the list
``ground-truth/baende.tsv`` + ``ground-truth/README.md``. Then rerun
``scripts/import_transkribus.py``, which applies the decision.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_transkribus as it  # noqa: E402

GT = {"GT", "DONE", "FINAL"}
ORDER = ["89729", "63705"]          # the collection 187323 was copied from first
NAMES = {"187323": "StABE_Turmbücher_DH_flow", "215878": "StABE_Turmbücher_DH_flow_GT",
         "89729": "StABE_Turmbücher_DH", "63705": "StABE_Turmbücher"}
RELEASE = "1. Juli 2027"


def text_of(path: Path) -> str:
    if not path.exists():
        return ""
    lines, _ = it.read_page(path)
    return "\n".join(" ".join(x["text"].split()) for x in lines if x["text"].strip())


def same_words(a: str, b: str) -> bool:
    """The same words, whatever their order and line breaks: a page whose lines were
    only re-ordered or split after the recognition still carries machine text."""
    return sorted(a.split()) == sorted(b.split())


def ranges(nums: list[int]) -> str:
    out, nums = [], sorted(set(nums))
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}–{nums[j]}")
        i = j + 1
    return ", ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "_ingest" / "vorbehalt")
    args = ap.parse_args()
    survey = [json.loads(x) for x in (args.src / "survey_cols.jsonl").open(encoding="utf-8")]
    idx = [json.loads(x) for x in (args.src / "htr_versions" / "index.jsonl").open(encoding="utf-8")]
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        pages = list(csv.DictReader(fh, delimiter="\t"))

    gt_where: dict[str, set[str]] = collections.defaultdict(set)
    for r in survey:
        if r["status"] in GT or r.get("any_gt"):
            gt_where[r["tk"]].add(r["col"] if not r["doc"].startswith("TRAINING") else r["col"] + " (Trainingsset)")
    htr: dict[str, tuple[str, Path, str]] = {}          # tk -> (col, path, tool) newest HTR, 89729 first
    latest: dict[str, tuple[str, Path]] = {}
    for col in ORDER:
        for r in idx:
            if r["col"] != col:
                continue
            p = args.src / "htr_versions" / "htr" / f"{col}_{r['tk']}.xml"
            if r.get("htr_ok") and p.exists() and r["tk"] not in htr:
                htr[r["tk"]] = (col, p, r.get("htr_tool") or "")
            q = args.src / "htr_versions" / "latest" / f"{col}_{r['tk']}.xml"
            if r.get("latest_ok") and q.exists() and r["tk"] not in latest:
                latest[r["tk"]] = (col, q)

    # pages whose latest version in 187323 is itself a recognition run (no later edit)
    own_htr = {}
    for x in (ROOT / "_ingest" / "manifest.jsonl").open(encoding="utf-8"):
        m = json.loads(x)
        v = (m.get("versions") or [{}])[0]
        own_htr[m["key"]] = bool(v.get("toolName")) and "Synced" not in v["toolName"] and v.get("transcribed_lines", 0) > 0
    pub = ROOT / "_ingest" / "pagexml_public"
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True)
    out, stats = [], collections.Counter()
    for p in pages:
        key, tk = p["key"], p["tk"]
        own = text_of(ROOT / "_ingest" / "pagexml" / f"{key}.xml")
        is_gt = tk in gt_where
        h = htr.get(tk)
        htext = text_of(h[1]) if h else ""
        row = {"key": key, "ground_truth": "ja" if is_gt else "", "text": "transkribus", "quelle": ""}
        if own:
            if not is_gt and own_htr.get(key):
                stats["Transkribus-Text = HTR-Ausgabe (in 187323 erkannt)"] += 1
            elif not is_gt and h and same_words(htext, own):
                stats["Transkribus-Text = HTR-Ausgabe"] += 1
            elif h and htext:
                row.update(text="htr", quelle=f"{h[0]}: {h[2][:80]}")
                shutil.copy(h[1], pub / f"{key}.xml")
                stats["ground truth: HTR-Fassung statt Text" if is_gt else "von Hand: HTR-Fassung statt Text"] += 1
            else:
                row.update(text="keiner")
                stats["ground truth: kein maschineller Transkribus-Text" if is_gt else "von Hand: kein maschineller Transkribus-Text"] += 1
        else:
            lt = latest.get(tk)
            if lt and not is_gt and h and text_of(lt[1]) == htext and htext:
                row.update(text="andere-sammlung", quelle=f"{lt[0]}: {h[2][:80]}")
                shutil.copy(lt[1], pub / f"{key}.xml")
                stats["leer, maschineller Text aus anderer Sammlung"] += 1
            elif h and htext and not is_gt:
                row.update(text="andere-sammlung", quelle=f"{h[0]}: {h[2][:80]}")
                shutil.copy(h[1], pub / f"{key}.xml")
                stats["leer, HTR-Fassung aus anderer Sammlung"] += 1
            elif h and htext and is_gt:
                row.update(text="htr", quelle=f"{h[0]}: {h[2][:80]}")
                shutil.copy(h[1], pub / f"{key}.xml")
                stats["leer, ground truth anderswo: HTR-Fassung"] += 1
            else:
                row.update(text="leer")
                stats["leer"] += 1
        row["gt_in"] = ", ".join(sorted(gt_where.get(tk, ())))
        out.append(row)

    with (ROOT / "readings" / "vorbehalt.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["key", "ground_truth", "text", "quelle", "gt_in"], delimiter="\t",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(out)

    # the list of Ground Truth per volume
    vol = {p["key"]: p for p in pages}
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for r in out:
        if r["ground_truth"]:
            by[vol[r["key"]]["volume"]].append(r)
    order = list(dict.fromkeys(p["volume"] for p in pages))
    gdir = ROOT / "ground-truth"
    gdir.mkdir(exist_ok=True)
    rows = []
    for v in order:
        if v not in by:
            continue
        cols = collections.Counter(c.strip() for r in by[v] for c in r["gt_in"].split(","))
        rows.append({"band": v, "seiten_gt": len(by[v]),
                     "seiten_band": sum(1 for p in pages if p["volume"] == v),
                     "seiten": ranges([int(vol[r["key"]]["pageNr"]) for r in by[v]]),
                     "markiert_in": "; ".join(f"{c} ({n})" for c, n in sorted(cols.items()))})
    with (gdir / "baende.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    total = sum(r["seiten_gt"] for r in rows)
    md = [f"# Ground Truth der Berner Turmbücher\n",
          f"Stand {__import__('datetime').date.today().strftime('%d.%m.%Y')}. Die Ground Truth – von Hand geprüfte "
          f"Transkriptionen – wird am **{RELEASE}** veröffentlicht. Bis dahin zeigen Viewer, Daten und TEI auf diesen "
          "Seiten nur maschinelle Lesungen.\n",
          f"**{len(rows)} Bände** mit zusammen **{total} Seiten** sind in Transkribus als Ground Truth markiert "
          "(Status GT, DONE oder FINAL in einer der Sammlungen "
          + ", ".join(f"{c} «{n}»" for c, n in NAMES.items())
          + ", in irgendeiner Fassung, oder Teil eines Trainings-/Validierungssets). Seiten werden über ihr Bild "
          "zugeordnet. Seitenzahlen = Bildnummer im Transkribus-Dokument der Sammlung 187323.\n",
          "| Band | GT-Seiten | Seiten im Band | Seiten | markiert in (Seiten) |", "|---|---:|---:|---|---|"]
    md += [f"| {r['band']} | {r['seiten_gt']} | {r['seiten_band']} | {r['seiten']} | {r['markiert_in']} |" for r in rows]
    md.append("\nMaschinenlesbar: `baende.tsv`; seitengenau: `../readings/vorbehalt.tsv` (Spalte `ground_truth`).\n")
    (gdir / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(out)} pages; " + "; ".join(f"{k}: {v}" for k, v in stats.most_common()))
    print(f"ground truth: {len(rows)} volumes, {total} pages")


if __name__ == "__main__":
    main()

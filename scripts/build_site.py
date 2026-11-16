"""Build the viewer's data from the readings of the Bernese Turmbücher.

    python scripts/build_site.py            # writes site/data/

The unit the viewer shows is a row of ``readings/units.tsv`` (id, shelf, nr,
title, pages). Until the entries are segmented (milestone M3) that file does
not exist and **every page is its own unit**: shelf = the volume (``B IX 422``),
nr = the page number in Transkribus. Later a unit is an entry of a Turmbuch,
with the pages it runs over.

Every reading is a machine's or an uncorrected working text unless a page's
Transkribus status says otherwise (``status``: GT, DONE, IN_PROGRESS). Where a
page has more than one reading, the build measures how much two readings
**disagree** — never how good either is.

Inputs
  readings/pages.tsv            every page (key, volume, pageNr, size, status, lines, tk)
  readings/units.tsv            optional: the units in order (see above)
  readings/<reader>.jsonl       one line per page: {"key": <page key>, "text": ...}
  readings/lines.jsonl          the Transkribus TextLines of each page: outline, text,
                                region type (scripts/import_transkribus.py)
  readings/readers.json         who each reader is (label, kind, about, caveat; German,
                                other languages as label_<lang> …)
  regests/drafts.jsonl          optional: machine-drafted heading and regest per unit
  entities/<reader>.jsonl       tags on a reading: {"key", "entities": [{start, end, type}]}

Outputs (site/data/)
  index.json                    units (id, shelf, nr, pages, thumbnail, status, draft
                                heading, year), volumes, search shard counts
  readers.json                  readers with pages read and pairwise disagreement
  units/<n>.json                CHUNK units in index order, each with its pages, every
                                reading, the image and the draft; a page with lines
                                carries ``rows`` (each line's outline), ``rt`` (the
                                region type of each row) and every reading ``ln`` (per
                                text line the rows it is linked to)
  pagekeys.json                 page key -> [unit id, page position]
  search/<reader>/text-<n>.json unit id -> page texts, loaded only by a search
"""

from __future__ import annotations

import csv
import itertools
import json
import shutil
import sys
from pathlib import Path

from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import line_links  # noqa: E402

NOT_READERS = {"lines"}         # readings/*.jsonl that hold no reading
OUT = ROOT / "site" / "data"
CHUNK = 20                      # units per file the viewer loads at once
SEARCH_SHARD_CHARS = 1_500_000  # text per search shard, loaded in parallel


def flat(text: str) -> str:
    return " ".join(text.split())


def clean_reading(text: str) -> str:
    """Drop the empty lines a line-based engine leaves for every segment it
    could not read; keep every other line."""
    return "\n".join(line.rstrip() for line in (text or "").splitlines() if line.strip())


def tsv(name: str) -> list[dict]:
    with (ROOT / "readings" / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_readings(known: set[str]) -> dict[str, dict[str, dict]]:
    readings: dict[str, dict[str, dict]] = {}
    for path in sorted((ROOT / "readings").glob("*.jsonl")):
        if path.stem in NOT_READERS:
            continue
        pages, unknown = {}, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec["key"] not in known:
                unknown.append(rec["key"])
                continue
            entry = {"text": clean_reading(rec.get("text", ""))}
            if rec.get("truncated"):
                entry["truncated"] = True
            pages[rec["key"]] = entry
        if unknown:
            print(f"  {path.name}: {len(unknown)} keys not in pages.tsv, e.g. {unknown[:3]}", file=sys.stderr)
        readings[path.stem] = pages
    return readings


def load_lines(known: set[str]) -> dict[str, dict]:
    """readings/lines.jsonl: per page key its rows (the TextLines, docs/LINES.md)."""
    out: dict[str, dict] = {}
    for path in sorted((ROOT / "readings" / "lines").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec["key"] in known and rec.get("poly"):
                    out[rec["key"]] = rec
    return out


def link_lines(rec: dict, geo: dict) -> dict[str, tuple[int, int]]:
    """Rows on the image for this page, and for every reading which rows each
    of its lines is on: ``rec["rows"]`` holds each TextLine's outline (x, y, x,
    y, ... in ten-thousandths of the image width), ``ln`` beside a reading per
    line the rows it is linked to, [] where no link was good enough. Returns
    per reader (lines linked, lines)."""
    rec["rows"] = geo["poly"]
    if any(geo.get("region") or []):
        rec["rt"] = geo["region"]
    row_texts = [[t] for t in geo["text"]]
    counts = {}
    for reader, entry in rec["readings"].items():
        if not entry.get("text"):
            continue
        ln = line_links.align(entry["text"].split("\n"), row_texts)
        entry["ln"] = ln
        counts[reader] = (sum(1 for x in ln if x), len(ln))
    return counts


def load_entities() -> dict[str, dict[str, list]]:
    """entities/<reader>.jsonl, same format as the St. Gallen viewer's:
    {"key": ..., "entities": [{"start", "end", "type", "text", "ref"?, ...}]}."""
    out: dict[str, dict[str, list]] = {}
    folder = ROOT / "entities"
    for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        pages = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                pages[rec["key"]] = rec["entities"]
        out[path.stem] = pages
    return out


def load_drafts(letter_ids: set[str]) -> dict[str, dict]:
    """regests/drafts.jsonl: the latest line per letter wins; a failed draft
    ({"error": ...}) shows nothing."""
    path = ROOT / "regests" / "drafts.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        d = rec.get("draft") or {}
        if rec.get("id") not in letter_ids:
            print(f"  drafts.jsonl: unknown letter {rec.get('id')}", file=sys.stderr)
            continue
        if "error" in d or not (d.get("regest") or "").strip():
            out.pop(rec["id"], None)
            continue
        year = d.get("year")
        out[rec["id"]] = {
            "heading": rec.get("heading") or "",
            "reader": rec.get("reader") or "",
            "model": rec.get("model") or "",
            "persons": d.get("persons") or [],
            "offences": d.get("offences") or [],
            "place": d.get("place") or "",
            "date_text": d.get("date_text") or "",
            "year": year if isinstance(year, int) else None,
            "year_source": d.get("year_source") or "",
            "regest": d["regest"].strip(),
        }
    return out


def write_search(letters: list[dict], readings: dict[str, dict[str, dict]], readers: list[str]) -> dict[str, int]:
    """Per reader: letter id -> the text of each of its pages ("" if unread),
    in the letter's page order (pages, then the further scans)."""
    out = OUT / "search"
    shards_of: dict[str, int] = {}
    for reader in readers:
        folder = out / reader
        folder.mkdir(parents=True, exist_ok=True)
        shards, cur, size = [], {}, 0
        for lt in letters:
            texts = [readings[reader].get(k, {}).get("text", "") for k in lt["keys"]]
            if not any(texts):
                continue
            while texts and not texts[-1]:
                texts.pop()
            cur[lt["id"]] = texts
            size += sum(len(t) for t in texts)
            if size >= SEARCH_SHARD_CHARS:
                shards.append(cur); cur, size = {}, 0
        if cur:
            shards.append(cur)
        for i, shard in enumerate(shards):
            (folder / f"text-{i}.json").write_text(json.dumps(shard, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        shards_of[reader] = len(shards)
    return shards_of


def load_units(pages: dict[str, dict]) -> list[dict]:
    """readings/units.tsv, or one unit per page while there is none."""
    path = ROOT / "readings" / "units.tsv"
    if path.exists():
        rows = tsv("units.tsv")
    else:
        rows = [{"id": k, "shelf": p["volume"], "nr": p["pageNr"], "title": "", "pages": k}
                for k, p in pages.items()]
    units, seen = [], set()
    for r in rows:
        keys = [k for k in r["pages"].split(";") if k]
        missing = [k for k in keys if k not in pages]
        if missing:
            sys.exit(f"units.tsv: {r['id']} names pages not in pages.tsv: {missing[:3]}")
        seen.update(keys)
        spans: dict[str, list[int]] = {}
        for k, a, b in json.loads(r["spans"]) if r.get("spans") else []:
            spans[k] = [a, b]           # the unit's lines on that page (0-based, in the reading it was cut on)
        units.append({**r, "keys": keys, "spans": spans})
    # a page in no unit (a volume not yet cut into entries, an empty page) is
    # its own unit, after the entries of its volume
    if path.exists():
        order = list(dict.fromkeys(p["volume"] for p in pages.values()))
        for k, p in pages.items():
            if k not in seen:
                units.append({"id": k, "shelf": p["volume"], "nr": p["pageNr"], "title": "", "keys": [k], "spans": {}, "page": True})
        units.sort(key=lambda u: (order.index(u["shelf"]), bool(u.get("page"))))
    else:
        for u in units:
            u["page"] = True
    return units


def write_analysis() -> None:
    """site/data/analysis.json for the charts: the vocabulary and, per described
    entry, [id, year, offences, sanctions, continuation, volume, title] with the
    vocabulary as indexes. Nothing is written while there are no entries."""
    path = ROOT / "entries" / "entries.jsonl"
    if not path.exists():
        return
    tax = json.loads((ROOT / "taxonomy" / "delikte.json").read_text(encoding="utf-8"))
    off = [d["id"] for d in tax["delikte"]]
    san = [d["id"] for d in tax["sanktionen"]]
    rows, vols = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if not e.get("regest") or e.get("kind") == "register":
            continue
        if e["volume"] not in vols:
            vols.append(e["volume"])
        rows.append([e["id"], e.get("year"), [off.index(o) for o in e["delikte"] if o in off],
                     [san.index(x) for x in e["sanktionen"]], 1 if e.get("fortsetzung") else 0,
                     vols.index(e["volume"]), e.get("title", "")])
    known = [g["id"] for g in tax.get("gruppen") or []]
    groups = [dict(g) for g in tax.get("gruppen") or []]
    for d in tax["delikte"]:            # a group named only on a category: listed, neutral colour
        if d["gruppe"] not in known:
            known.append(d["gruppe"])
            groups.append({"id": d["gruppe"], "farbe": "#898781"})
    out = {"version": tax.get("version", 1), "groups": groups,
           "offences": [{"id": d["id"], "label": d["label"], "group": d["gruppe"], "hint": d.get("hinweis", "")} for d in tax["delikte"]],
           "sanctions": [{"id": d["id"], "label": d["label"]} for d in tax["sanktionen"]],
           "volumes": vols, "entries": rows,
           "model": sorted({json.loads(x)["model"] for x in path.read_text(encoding="utf-8").splitlines() if json.loads(x).get("model")})}
    (OUT / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    pages = {p["key"]: p for p in tsv("pages.tsv")}
    letters = load_units(pages)
    readings = load_readings(set(pages))
    lines = load_lines(set(pages))
    entities = load_entities()
    listed = json.loads((ROOT / "readings" / "readers.json").read_text(encoding="utf-8"))
    for r in listed:
        if r["id"] not in readings:
            print(f"  reader {r['id']}: no readings/{r['id']}.jsonl yet — not shown", file=sys.stderr)
    for rid in readings:
        if rid not in {r["id"] for r in listed}:
            print(f"  readings/{rid}.jsonl: not in readers.json — not shown", file=sys.stderr)
    readers = [r for r in listed if readings.get(r["id"])]
    ids = [r["id"] for r in readers]
    drafts = load_drafts({r["id"] for r in letters})
    seen = {k for lt in letters for k in lt["keys"]}

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "units").mkdir(parents=True)

    pair = {(a, b): {"edits": 0, "chars": 0, "pages": 0} for a, b in itertools.combinations(ids, 2)}
    read = {r: 0 for r in ids}
    counted: set[tuple[str, str]] = set()
    linked = {r: [0, 0] for r in ids}   # lines linked, lines on pages with rows
    index, pagekeys, chunk = [], {}, []
    for pos, lt in enumerate(letters):
        recs = []
        for i, key in enumerate(lt["keys"]):
            p = pages[key]
            pagekeys[key] = [lt["id"], i + 1]
            num = lambda v: int(v) if str(v).isdigit() else None  # noqa: E731
            rec = {"key": key, "vol": p["volume"], "nr": num(p["pageNr"]), "tk": p.get("tk", ""),
                   "w": num(p.get("width", "")), "h": num(p.get("height", "")),
                   "st": p.get("status", ""), "lines": num(p.get("lines", "")), "readings": {}}
            if key in lt.get("spans", {}):
                rec["span"] = lt["spans"][key]
            for r in ids:
                rd = readings[r].get(key)
                if rd is not None:
                    rec["readings"][r] = rd
                    if (r, key) not in counted:      # a page shared by two units is read once
                        counted.add((r, key))
                        read[r] += 1
            dis = {}
            for a, b in itertools.combinations([r for r in ids if rec["readings"].get(r, {}).get("text")], 2):
                ta, tb = flat(rec["readings"][a]["text"]), flat(rec["readings"][b]["text"])
                edits = Levenshtein.distance(ta, tb)
                longer = max(len(ta), len(tb))
                dis[f"{a}|{b}"] = round(edits / longer, 4)
                t = pair[(a, b)]
                t["edits"] += edits; t["chars"] += longer; t["pages"] += 1
            if dis:
                rec["dis"] = dis
            if key in lines:
                for r, (a, b) in link_lines(rec, lines[key]).items():
                    linked[r][0] += a
                    linked[r][1] += b
            for r, ents in entities.items():
                if key in ents and r in rec["readings"]:
                    rec.setdefault("ents", {})[r] = ents[key]
            recs.append(rec)
        d = drafts.get(lt["id"])
        full = {"id": lt["id"], "shelf": lt["shelf"], "nr": lt["nr"], "title": lt.get("title", ""), "pages": recs}
        if d:
            full["draft"] = d
        chunk.append(full)
        row = {"id": lt["id"], "shelf": lt["shelf"], "nr": lt["nr"], "n": len(recs),
               "tk": recs[0]["tk"] if recs else ""}
        if lt.get("page"):
            row["p"] = 1
            full["p"] = 1
        sts = {x["st"] for x in recs}
        if len(sts) == 1 and recs[0]["st"]:
            row["st"] = recs[0]["st"]
        if not any(x["readings"] for x in recs):
            row["e"] = 1        # no reading at all
        if d:
            row.update({"h": d["heading"], "y": d["year"], "o": d["offences"]})
        index.append(row)
        if len(chunk) == CHUNK or pos == len(letters) - 1:
            (OUT / "units" / f"{pos // CHUNK}.json").write_text(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            chunk = []

    for r in readers:
        r["pages_read"] = read[r["id"]]
        r["entities"] = r["id"] in entities
        r["disagreement"] = {}
    by_id = {r["id"]: r for r in readers}
    for (a, b), t in pair.items():
        if t["pages"]:
            x = {"value": round(t["edits"] / t["chars"], 4), "pages": t["pages"]}
            by_id[a]["disagreement"][b] = x
            by_id[b]["disagreement"][a] = x

    shards = write_search(letters, readings, ids)
    vols: dict[str, dict] = {}
    for p in pages.values():
        v = vols.setdefault(p["volume"], {"v": p["volume"], "doc": p["volume"] if p["volume"] == "Henzi" else p["doc"], "pages": 0, "gt": 0, "text": 0})
        v["pages"] += 1
        v["gt"] += p.get("status") in ("GT", "DONE", "FINAL")
        v["text"] += int(p.get("text_lines") or 0) > 0
    write_analysis()
    if (ROOT / "entries" / "entries.jsonl").exists():      # TEI, one file per volume (scripts/tei_export.py)
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "tei_export.py"), "--out", str(OUT / "tei")], check=True)
    reg = ROOT / "register" / "orte.json"
    check = ROOT / "pruefung" / "stichprobe.json"
    if check.exists():      # the sample for checking by hand (scripts/pruefung.py)
        shutil.copyfile(check, OUT / "pruefung.json")
    pers = ROOT / "register" / "personen.json"
    if pers.exists():       # the register of persons (scripts/register.py)
        shutil.copyfile(pers, OUT / "register_personen.json")
    if reg.exists():        # the map's places (scripts/places.py); the viewer joins them to analysis.json by entry id
        shutil.copyfile(reg, OUT / "map.json")
    out = {"chunk": CHUNK, "analysis": (OUT / "analysis.json").exists(), "map": (OUT / "map.json").exists(), "pages": len(pages),
           "volumes": list(vols.values()), "units": index, "search": shards}
    (OUT / "index.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "pagekeys.json").write_text(json.dumps(pagekeys, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "readers.json").write_text(json.dumps(readers, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(pages)} pages in {len(letters)} units, {len(drafts)} with a drafted regest; "
          f"{sum(1 for k in lines if k in seen)} with line outlines")
    for r in readers:
        a, b = linked[r["id"]]
        print(f"  {r['id']:<40} read {r['pages_read']:>5}; lines linked to the image {a} of {b}"
              f"{f' ({a / b:.1%})' if b else ''}")
    for (a, b), t in pair.items():
        if t["pages"]:
            print(f"  disagreement {a} | {b}: {t['edits'] / t['chars']:.4f} over {t['pages']} pages")


if __name__ == "__main__":
    main()

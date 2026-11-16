"""A sample for checking the machine's work by hand.

    python scripts/pruefung.py            # → pruefung/stichprobe.json (fixed seed: the same sample every time)

Three tasks, shown in the viewer under #/pruefen:

``grenzen``   50 pages, one each from 50 volumes spread evenly over the series:
              the page's lines with the entry starts the model set. The reviewer
              moves, adds or removes starts.
``delikte``   80 entries, up to three per offence category (so rare categories
              are checked too), the rest at random: offences, outcome, year,
              the accused in the title, the regest.
``personen``  every «wahrscheinlich» link to the HLS and 20 «möglich» ones:
              is the person in the entries the person in the lexicon?

The sample is drawn from the data as it stands; drawing it again after the
data changed gives a different sample, so the file is committed and carries
its date. Evaluation: scripts/pruefung_auswerten.py.
"""

from __future__ import annotations

import collections
import csv
import datetime
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261116
N_PAGES, N_ENTRIES, PER_OFFENCE, N_POSSIBLE = 50, 80, 3, 20
MAX_LINES = 140


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def vol_number(v: str) -> int:
    m = re.search(r"(\d+)", v)
    return int(m.group(1)) if m else 10 ** 6


def main() -> None:
    rnd = random.Random(SEED)
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        pages = {r["key"]: r for r in csv.DictReader(fh, delimiter="\t")}
    text = {r["key"]: r["text"].split("\n") for r in jsonl(ROOT / "readings" / "transkribus-bestand.jsonl")}
    segs = {}
    for r in jsonl(ROOT / "entries" / "segments.jsonl"):
        if r.get("reader") == "transkribus-bestand" and "error" not in r:
            segs[r["key"]] = r
    entries = [e for e in jsonl(ROOT / "entries" / "entries.jsonl")]

    def page(key: str, first: int = 0, last: int | None = None) -> dict:
        p = pages[key]
        lines = text.get(key, [])
        last = len(lines) - 1 if last is None else last
        return {"key": key, "vol": p["volume"], "nr": int(p["pageNr"]), "tk": p["tk"], "st": p["status"],
                "first": first, "lines": lines[first:last + 1][:MAX_LINES]}

    # --- boundaries: one page per volume, 50 volumes spread over the series
    by_vol = collections.defaultdict(list)
    order = list(dict.fromkeys(p["volume"] for p in pages.values()))
    for key, s in segs.items():
        if s["art"] == "verhoer" and len(text.get(key, [])) >= 8:
            by_vol[pages[key]["volume"]].append(key)
    vols = sorted(by_vol, key=lambda v: (vol_number(v), v))
    step = len(vols) / N_PAGES
    chosen = [vols[int(i * step)] for i in range(min(N_PAGES, len(vols)))]
    grenzen = []
    for v in chosen:
        key = rnd.choice(sorted(by_vol[v]))
        keys = [k for k in pages if pages[k]["volume"] == v]
        i = keys.index(key)
        before = text.get(keys[i - 1], [])[-4:] if i > 0 else []
        grenzen.append({**page(key), "before": before, "starts": [s - 1 for s in segs[key]["starts"]]})

    # --- offences: up to three entries per category, then at random
    described = [e for e in entries if e.get("regest") and e.get("delikte") and e.get("kind") != "register"]
    by_off = collections.defaultdict(list)
    for e in described:
        by_off[e["delikte"][0]].append(e)
    pick, seen = [], set()
    for off in sorted(by_off):
        for e in rnd.sample(by_off[off], min(PER_OFFENCE, len(by_off[off]))):
            if e["id"] not in seen:
                pick.append(e)
                seen.add(e["id"])
    rest = [e for e in described if e["id"] not in seen]
    pick += rnd.sample(rest, max(0, N_ENTRIES - len(pick)))
    rnd.shuffle(pick)
    delikte = []
    for e in pick[:max(N_ENTRIES, len(pick))]:
        acc = [p["name"] for p in e.get("personen") or [] if p["rolle"] == "beschuldigt"]
        delikte.append({"id": e["id"], "vol": e["volume"], "year": e.get("year"), "year_source": e.get("year_source", ""),
                        "datum_text": e.get("datum_text", ""), "title": e.get("title", ""), "accused": acc,
                        "delikte": e["delikte"], "sanktionen": e.get("sanktionen") or [], "regest": e.get("regest", ""),
                        "woertlich": e.get("delikt_woertlich", ""),
                        "pages": [page(k, a, b) for k, a, b in e["spans"]]})

    # --- persons: every probable HLS link and some possible ones
    persons = json.loads((ROOT / "register" / "personen.json").read_text(encoding="utf-8"))["persons"]
    eidx = {e["id"]: e for e in entries}
    likely, possible = [], []
    for r in persons:
        for h in r.get("hls") or []:
            (likely if h["grade"] == "wahrscheinlich" else possible).append((r, h))
    personen = []
    for r, h in likely + rnd.sample(possible, min(N_POSSIBLE, len(possible))):
        ex = []
        for eid in h["entries"][:3]:
            e = eidx.get(eid)
            if e:
                roles = [p["rolle"] for p in e.get("personen") or [] if p["name"] in r["forms"]]
                ex.append({"id": eid, "year": e.get("year"), "title": e.get("title", ""), "regest": e.get("regest", ""), "roles": roles})
        personen.append({"key": f'{r["key"]}|{h["hls"]}', "name": r["name"], "forms": r["forms"], "years": r["years"],
                         "roles": r["roles"], "grade": h["grade"], "n": len(h["entries"]),
                         "hls": {k: h.get(k) for k in ("hls", "qid", "gnd", "name", "b", "d", "desc")}, "entries": ex})

    out = {"version": datetime.date.today().isoformat(), "seed": SEED,
           "grenzen": grenzen, "delikte": delikte, "personen": personen}
    (ROOT / "pruefung").mkdir(exist_ok=True)
    (ROOT / "pruefung" / "stichprobe.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"sample {out['version']}: {len(grenzen)} pages from {len(chosen)} volumes, {len(delikte)} entries "
          f"({len(by_off)} first offences), {len(personen)} person links ({len(likely)} probable)")


if __name__ == "__main__":
    main()

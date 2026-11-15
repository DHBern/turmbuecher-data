"""Entries of the Turmbücher: where they begin, and what each one is about.

    python scripts/entries.py segment [--volumes "B IX 467"] [--reader transkribus-bestand]
    python scripts/entries.py extract [--volumes …]
    python scripts/entries.py build

Three steps, each resumable (a page or entry already answered is not asked again):

``segment``  One call per page to an open language model (scripts/llm.py): the
             page's lines, numbered, with the end of the previous page as context
             and the lines Transkribus' layout calls a heading marked. The model
             answers with **line numbers only** (where an entry begins) and the
             kind of page. → ``entries/segments.jsonl``
``extract``  One call per entry: date, persons, offences (from the fixed list in
             ``taxonomy/delikte.json``), procedure, sanctions, places, a short
             regest. → ``entries/extract.jsonl``
``build``    Puts both together, checks the years against the volume, builds the
             title from the fields (never free text), and writes
             ``entries/entries.jsonl`` (the record), ``readings/units.tsv`` (the
             viewer's units) and ``regests/drafts.jsonl`` (title and regest).

Everything here is a machine's work on a mostly uncorrected machine reading.
Nothing is checked by a person; every output says which model and reading it
came from.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import llm  # noqa: E402

ENT = ROOT / "entries"
CONTEXT_LINES = 12
MAX_HEAD, MAX_TAIL = 9000, 2000
WORKERS = 6
TAX = json.loads((ROOT / "taxonomy" / "delikte.json").read_text(encoding="utf-8"))
OFF = {d["id"]: d for d in TAX["delikte"]}
PROC = {d["id"]: d for d in TAX["verfahren"]}
SANC = {d["id"]: d for d in TAX["sanktionen"]}

SEG_SYSTEM = """Du gliederst ein Berner Turmbuch in Einträge. Turmbücher sind Verhörprotokolle der Berner Obrigkeit (16.–18. Jahrhundert), frühneuhochdeutsch. Der Text ist maschinell gelesen und enthält viele Lesefehler.

Ein Eintrag ist das Verhör oder der Fall einer Person (oder einer gemeinsam verhörten Gruppe). Ein neuer Eintrag beginnt
- mit einer Überschrift, die den Namen der verhörten Person nennt (oft mit Herkunft), oder
- mit einer Datumszeile, die ein Verhör einleitet («Uff Mittwuch dem 22. tag Novembris 1564 … hatt N. N. … verjechen»), oder
- mit einer Formel wie «N. N. von X hat bekennt», wenn davor ein anderer Fall endet.
Ein weiteres Verhör derselben Person an einem anderen Tag ist ein neuer Eintrag.

KEIN neuer Eintrag sind: einzelne Punkte eines Geständnisses («Denne …», «Item …», «Erstlich …»), Fragen und Antworten innerhalb eines Verhörs, Urteils- und Schlussvermerke («Actum …», «ist ledig gelassen worden»), Seitenzahlen, Randnotizen, Kustoden.

Zeilen, die das Layout als Überschrift kennzeichnet, tragen [Ü]. Mehrere [Ü]-Zeilen hintereinander sind eine Überschrift: Der Eintrag beginnt bei der ersten.

Antworte nur mit JSON: {"starts": [Zeilennummern der SEITE, an denen ein Eintrag beginnt], "art": "verhoer" | "register" | "titel" | "leer" | "anderes"}
"art" beschreibt die Seite: "register" für ein Namens- oder Inhaltsverzeichnis, "titel" für Titelblatt oder Einband, "leer" für (fast) leere Seiten. Bei register, titel und leer ist "starts" leer. Setzt die Seite nur einen Eintrag der vorigen Seite fort, ist "starts" leer."""

EXT_SYSTEM = """Du erschliesst einen Eintrag aus einem Berner Turmbuch (Verhörprotokolle der Berner Obrigkeit, 16.–18. Jahrhundert, frühneuhochdeutsch). Der Text ist maschinell gelesen und enthält viele Lesefehler; lies über sie hinweg, aber erfinde nichts. Was nicht im Text steht, bleibt leer (null oder []).

Antworte nur mit einem JSON-Objekt mit genau diesen Feldern:
{
 "art": "verhoer" | "urteil" | "urfehde" | "register" | "anderes",
 "datum_text": Datum des Verhörs, wie es im Text steht, oder null,
 "datum": dasselbe als "JJJJ-MM-TT", "JJJJ-MM" oder "JJJJ", oder null (Monat und Tag nur, wenn sie eindeutig dastehen; keine Umrechnung von Festtagen),
 "personen": [{"name": Name in lesbarer, quellennaher Schreibung, "rolle": "beschuldigt" | "opfer" | "zeuge" | "amtsperson" | "andere", "herkunft": Ort oder null, "geschlecht": "m" | "w" | "u"}],
 "delikte": [Kennungen aus der Liste unten; alle Vorwürfe gegen die beschuldigte Person, höchstens 4, der wichtigste zuerst],
 "delikt_woertlich": der Vorwurf mit den Worten der Quelle, kurz, oder null,
 "verfahren": [Kennungen aus der Liste; "peinlich" nur, wenn Folter oder peinliche Befragung genannt ist],
 "sanktionen": [Kennungen aus der Liste; nur, was der Text als Urteil oder Ausgang nennt],
 "orte": [Orte, an denen etwas geschah oder aus denen Personen stammen, in heutiger Schreibung, wo sie sicher erkennbar ist, sonst wie in der Quelle],
 "regest": zwei bis drei Sätze in heutigem Deutsch: wer, was wird vorgeworfen oder gestanden, Ausgang. Namen wie in "personen". Keine Vermutungen, kein Kommentar zur Textqualität.,
 "fortsetzung": true, wenn der Eintrag ein früheres Verhör derselben Person fortsetzt («wyther», «abermals», «zum andern mal»), sonst false
}

DELIKTE:
%s

VERFAHREN:
%s

SANKTIONEN:
%s""" % (
    "\n".join(f"- {d['id']}: {d['label']} ({d['hinweis']})" for d in TAX["delikte"]),
    "\n".join(f"- {d['id']}: {d['label']}" for d in TAX["verfahren"]),
    "\n".join(f"- {d['id']}: {d['label']}" + (f" ({d['hinweis']})" if d.get("hinweis") else "") for d in TAX["sanktionen"]),
)


# ---------- data ----------
def pages() -> list[dict]:
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def page_lines(reader: str) -> dict[str, list[tuple[str, bool]]]:
    """Per page key the text lines of ``reader`` with a heading flag (from the
    Transkribus layout, where the line counts agree; else no flags)."""
    texts = {r["key"]: r["text"].split("\n") for r in jsonl(ROOT / "readings" / f"{reader}.jsonl")}
    geo = {r["key"]: r for path in sorted((ROOT / "readings" / "lines").glob("*.jsonl")) for r in jsonl(path)}
    out = {}
    for key, lines in texts.items():
        g = geo.get(key)
        flags = [False] * len(lines)
        if g:
            rows = [(t, r) for t, r in zip(g["text"], g.get("region") or [""] * len(g["text"])) if t.strip()]
            if [t for t, _ in rows] == lines:
                flags = [r == "heading" for _, r in rows]
        out[key] = list(zip(lines, flags))
    return out


def selected(args) -> list[dict]:
    want = [v.strip() for v in (args.volumes or "").split(",") if v.strip()]
    return [p for p in pages() if not want or p["volume"] in want]


class Log:
    """Append-only JSONL, one answer per line; the latest line per id wins."""

    def __init__(self, path: Path, idkey: str):
        self.path, self.lock = path, threading.Lock()
        path.parent.mkdir(exist_ok=True)
        self.done = {r[idkey] for r in jsonl(path) if "error" not in r}

    def add(self, rec: dict) -> None:
        with self.lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run(items: list, work, label: str) -> None:
    n = [0, 0]

    def one(item):
        try:
            work(item)
        except Exception as e:  # noqa: BLE001
            n[1] += 1
            print(f"  failed: {repr(e)[:160]}", file=sys.stderr, flush=True)
        n[0] += 1
        if n[0] % 50 == 0:
            print(f"{label}: {n[0]}/{len(items)} ({n[1]} failed)", flush=True)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, items))
    print(f"{label}: {len(items)} asked, {n[1]} failed", flush=True)


# ---------- segment ----------
def segment(args) -> None:
    lines = page_lines(args.reader)
    log = Log(ENT / "segments.jsonl", "key")
    todo, prev = [], {}
    last_by_vol: dict[str, str] = {}
    for p in selected(args):
        key = p["key"]
        if key in lines:
            prev[key] = last_by_vol.get(p["volume"])
            last_by_vol[p["volume"]] = key
            if key not in log.done:
                todo.append(key)

    def work(key: str) -> None:
        ctx = [t for t, _ in lines.get(prev.get(key) or "", [])][-CONTEXT_LINES:]
        body = "\n".join(f"{i + 1}{' [Ü]' if h else ''}: {t}" for i, (t, h) in enumerate(lines[key]))
        user = ("KONTEXT (Ende der vorigen Seite, nicht gliedern):\n" + ("\n".join(ctx) if ctx else "(Bandanfang)") +
                "\n\nSEITE:\n" + body)
        ans = llm.parse_json(llm.chat(SEG_SYSTEM, user, 300))
        n = len(lines[key])
        starts = sorted({int(x) for x in ans.get("starts") or [] if str(x).isdigit() and 1 <= int(x) <= n})
        log.add({"key": key, "starts": starts, "art": str(ans.get("art") or ""), "lines": n,
                 "reader": args.reader, "model": llm.MODEL})

    run(todo, work, "segment")


# ---------- entries from the segments ----------
def entry_list(reader: str) -> list[dict]:
    """The entries in order: id, volume, the (page key, first line, last line)
    spans they run over. Text before a volume's first start is entry 0 of the
    volume (front matter or the end of a case begun in another volume)."""
    segs = {r["key"]: r for r in jsonl(ENT / "segments.jsonl") if "error" not in r and r.get("reader") == reader}
    lines = page_lines(reader)
    out, cur, vol, n = [], None, None, 0
    for p in pages():
        key = p["key"]
        if key not in lines or key not in segs:
            continue
        if p["volume"] != vol:
            vol, n, cur = p["volume"], 0, None
        seg = segs[key]
        cuts = [s - 1 for s in seg["starts"]]
        bounds = sorted(set([0] + cuts)) + [len(lines[key])]
        for a, b in zip(bounds, bounds[1:]):
            if b <= a:
                continue
            if a in cuts or cur is None:
                cur = {"id": f"{key.rsplit('_p', 1)[0]}_e{n:04d}", "volume": vol, "nr": n, "spans": [],
                       "kind": seg["art"] if a not in cuts else "verhoer"}
                n += 1
                out.append(cur)
            cur["spans"].append([key, a, b - 1])
    return out


def entry_text(e: dict, lines: dict) -> str:
    return "\n".join(t for key, a, b in e["spans"] for t, _ in lines[key][a:b + 1])


# ---------- extract ----------
def extract(args) -> None:
    lines = page_lines(args.reader)
    docs = {p["volume"]: p["doc"] for p in pages()}
    want = {p["volume"] for p in selected(args)}
    log = Log(ENT / "extract.jsonl", "id")
    todo = [e for e in entry_list(args.reader) if e["volume"] in want and e["id"] not in log.done
            and e["kind"] not in ("register", "titel", "leer")]

    def work(e: dict) -> None:
        text = entry_text(e, lines)
        if len(text) > MAX_HEAD + MAX_TAIL:
            text = text[:MAX_HEAD] + "\n[…]\n" + text[-MAX_TAIL:]
        user = f"Band: {docs[e['volume']]}\n\nEINTRAG:\n{text}"
        ans = llm.parse_json(llm.chat(EXT_SYSTEM, user, 2500))
        if not isinstance(ans, dict):
            raise ValueError("not an object")
        log.add({"id": e["id"], "spans": e["spans"], "chars": len(text), "reader": args.reader,
                 "model": llm.MODEL, "x": ans})

    run(todo, work, "extract")


# ---------- build ----------
def year_of(s) -> int | None:
    m = re.match(r"^(1[4-8]\d\d)", str(s or ""))
    return int(m.group(1)) if m else None


def title_span(doc: str) -> tuple[int, int] | None:
    m = re.search(r"\((1[4-8]\d\d)\s*[-–]\s*(1[4-8]\d\d)\)", doc)
    return (int(m.group(1)), int(m.group(2))) if m else None


def clean(x: dict) -> dict:
    """Keep only what the schema allows; unknown codes are dropped, never guessed."""
    def codes(v, allowed):
        return [c for c in dict.fromkeys(v if isinstance(v, list) else []) if c in allowed]
    persons = []
    for p in x.get("personen") if isinstance(x.get("personen"), list) else []:
        if isinstance(p, dict) and str(p.get("name") or "").strip():
            persons.append({"name": str(p["name"]).strip(),
                            "rolle": p.get("rolle") if p.get("rolle") in ("beschuldigt", "opfer", "zeuge", "amtsperson", "andere") else "andere",
                            "herkunft": str(p.get("herkunft") or "").strip(),
                            "geschlecht": p.get("geschlecht") if p.get("geschlecht") in ("m", "w") else "u"})
    off = codes(x.get("delikte"), OFF)[:4]
    if len(off) > 1:
        off = [c for c in off if c != "unklar"] or ["unklar"]
    return {"art": str(x.get("art") or ""), "datum_text": str(x.get("datum_text") or "").strip(),
            "datum": str(x.get("datum") or "").strip(), "personen": persons, "delikte": off,
            "delikt_woertlich": str(x.get("delikt_woertlich") or "").strip(),
            "verfahren": codes(x.get("verfahren"), PROC), "sanktionen": codes(x.get("sanktionen"), SANC),
            "orte": [str(o).strip() for o in (x.get("orte") if isinstance(x.get("orte"), list) else []) if str(o).strip()],
            "regest": str(x.get("regest") or "").strip(), "fortsetzung": bool(x.get("fortsetzung"))}


def make_title(c: dict) -> str:
    """Offence(s) — accused, from the fields: «Diebstahl / Ehebruch — Hans Müller von Thun»."""
    labels = [OFF[o]["label"] for o in c["delikte"] if o != "unklar"]
    what = " / ".join(labels) if labels else "Vorwurf unklar"
    acc = [p for p in c["personen"] if p["rolle"] == "beschuldigt"]
    if not acc:
        return f"{what} — ohne Namen"
    who = acc[0]["name"] + (f" von {acc[0]['herkunft']}" if acc[0]["herkunft"] and acc[0]["herkunft"].lower() not in acc[0]["name"].lower() else "")
    if len(acc) > 1:
        who += f" und {len(acc) - 1} weitere" if len(acc) > 2 else f" und {acc[1]['name']}"
    return f"{what} — {who}"


def build(args) -> None:
    entries = entry_list(args.reader)
    ext = {r["id"]: r for r in jsonl(ENT / "extract.jsonl") if "error" not in r and r.get("reader") == args.reader}
    docs = {p["volume"]: p["doc"] for p in pages()}
    by_vol: dict[str, list[dict]] = {}
    for e in entries:
        r = ext.get(e["id"])
        e["x"] = clean(r["x"]) if r else None
        e["model"] = r["model"] if r else ""
        by_vol.setdefault(e["volume"], []).append(e)

    # years: within the volume's span (from its title, else from the bulk of the
    # years read in it); a year outside is not believed and the last good one is kept
    report = []
    for vol, es in by_vol.items():
        years = [y for e in es if e["x"] and (y := year_of(e["x"]["datum"]))]
        span = title_span(docs[vol])
        src = "Titel"
        if not span and len(years) >= 5:
            q = statistics.quantiles(years, n=10)
            span, src = (int(q[0]) - 2, int(q[-1]) + 2), "gelesene Jahre"
        last, out_of = None, 0
        for e in es:
            if not e["x"]:
                continue
            y = year_of(e["x"]["datum"])
            if y and span and not (span[0] - 1 <= y <= span[1] + 1):
                y, out_of = None, out_of + 1
            if y:
                e["year"], e["year_source"], last = y, "genannt", y
            elif last:
                e["year"], e["year_source"] = last, "vom vorangehenden Eintrag"
            else:
                e["year"], e["year_source"] = None, ""
        report.append(f"  {vol}: {len(es)} entries, {sum(1 for e in es if e['x'])} described, span {span} ({src if span else '—'}), "
                      f"{out_of} years outside the span dropped")

    ENT.mkdir(exist_ok=True)
    (ROOT / "regests").mkdir(exist_ok=True)
    rec, units, drafts = [], [], []
    for e in entries:
        x = e["x"]
        keys = list(dict.fromkeys(k for k, _, _ in e["spans"]))
        title = make_title(x) if x and x["art"] != "register" else ""
        rec.append({"id": e["id"], "volume": e["volume"], "nr": e["nr"], "kind": (x or {}).get("art") or e["kind"],
                    "spans": e["spans"], "year": e.get("year"), "year_source": e.get("year_source", ""),
                    "title": title, "reader": args.reader, "model": e["model"], **(x or {})})
        units.append({"id": e["id"], "shelf": e["volume"], "nr": e["nr"], "title": "", "pages": ";".join(keys),
                      "spans": json.dumps(e["spans"], separators=(",", ":"))})
        if x and x["regest"]:
            drafts.append({"id": e["id"], "heading": title, "reader": args.reader, "model": e["model"],
                           "draft": {"regest": x["regest"], "year": e.get("year"), "date_text": x["datum_text"],
                                     "persons": x["personen"], "offences": x["delikte"], "place": ""}})
    for path, rows in ((ENT / "entries.jsonl", rec), (ROOT / "regests" / "drafts.jsonl", drafts)):
        tmp = path.with_suffix(".part")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(path)
    with (ROOT / "readings" / "units.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(units[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(units)
    print(f"{len(rec)} entries, {len(drafts)} with a regest")
    print("\n".join(report))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["segment", "extract", "build"])
    ap.add_argument("--volumes", default="")
    ap.add_argument("--reader", default="transkribus-bestand")
    args = ap.parse_args()
    {"segment": segment, "extract": extract, "build": build}[args.step](args)


if __name__ == "__main__":
    main()

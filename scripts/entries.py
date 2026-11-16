"""Entries of the Turmbücher: where they begin, and what each one is about.

    python scripts/entries.py segment [--volumes "B IX 467"] [--reader transkribus-bestand]
    python scripts/entries.py extract [--volumes …]
    python scripts/entries.py build
    python scripts/entries.py relabel             # after the vocabulary has grown
    python scripts/entries.py vorschlaege         # what the vocabulary does not cover yet

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

``relabel``  The vocabulary is meant to grow (taxonomy/README.md). Every answer
             records the vocabulary ``version`` it was given under; after the
             version is raised, ``relabel`` asks again for the **offences only**
             of the entries labelled under an older version, showing the model
             the labels the entry has and the categories added since, and
             writes them to ``entries/labels.jsonl``; ``build`` lets the newest
             labels win. Dates, persons and regests are not redone.
``vorschlaege`` Lists what the model could not place (``sonstiges``, ``unklar``)
             with the source's own words and the category the model would have
             wanted, most frequent first → ``entries/vorschlaege.tsv``: the
             material for the next category.

Everything here is a machine's work on a mostly uncorrected machine reading.
Nothing is checked by a person; every output says which model and reading it
came from.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
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
VERSION = int(TAX.get("version") or 1)
OFF = {d["id"]: d for d in TAX["delikte"]}
ALIAS = {a: d["id"] for d in TAX["delikte"] for a in d.get("alias") or []}   # earlier ids of a category
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
 "delikt_vorschlag": nur wenn kein Delikt der Liste passt ("sonstiges"): eine kurze heutige Bezeichnung für die fehlende Kategorie, sonst null,
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
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                out.append(json.loads(x))
            except ValueError:      # a run may be writing its last line right now
                pass
    return out


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
                 "model": llm.MODEL, "tax": VERSION, "x": ans})

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
        v = [ALIAS.get(c, c) if isinstance(c, str) else c for c in (v if isinstance(v, list) else [])]
        return [c for c in dict.fromkeys(v) if isinstance(c, str) and c in allowed]
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
            "delikt_vorschlag": str(x.get("delikt_vorschlag") or "").strip(),
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


WINDOW = 3          # a volume's years cluster within ± this many years of its centre
SLIPS = (50, -50, 100, -100)   # the misreadings seen: a year off by exactly half a century or a century


def vol_number(vol: str) -> int:
    m = re.search(r"(\d+)", vol)
    return int(m.group(1)) if m else 10 ** 6


def volume_years(by_vol: dict[str, list[dict]], docs: dict[str, str]) -> list[str]:
    """Give every described entry ``year`` and ``year_source``.

    The volumes are in chronological order and each covers a few years. The
    model reads many years wrong by exactly 50 or 100 (1520 for 1570, 1684 for
    1584), so a year is believed only inside its volume's span:

    * the span is the one known for the volume (taxonomy/bandjahre.json) or the
      one in its title, where there is one; else the
      densest cluster of the years read in the volume, and of several clusters
      the one that fits between the neighbouring volumes;
    * a year outside the span that falls inside it when moved by 50 or 100, or
      by changing its tens digit (only when exactly one such year fits), is
      corrected (``berichtigt``); any other year outside is dropped, and the
      entry takes the year of the entry before it (``vom vorangehenden Eintrag``);
    * every entry whose year read disagrees with the span gets a note
      (``year_note``), and ``entries/datierung_vermerke.md`` lists them, with
      the volumes whose years read mostly fall outside their known span.
    """
    order = sorted((v for v in by_vol if re.match(r"^B IX \d+", v)), key=vol_number)
    years = {v: [y for e in by_vol[v] if e["x"] and (y := year_of(e["x"]["datum"]))] for v in by_vol}
    known = json.loads((ROOT / "taxonomy" / "bandjahre.json").read_text(encoding="utf-8"))
    fixed = {v: (known[v]["von"], known[v]["bis"]) if isinstance(known.get(v), dict) else title_span(docs[v])
             for v in by_vol}

    def clusters(v: str) -> list[tuple[int, int]]:
        """(entries within the window, centre) for every year read, best first."""
        ys = years[v]
        return sorted(((sum(1 for y in ys if abs(y - c) <= WINDOW), c) for c in set(ys)), reverse=True)

    centre: dict[str, float | None] = {}
    for v in by_vol:
        if fixed[v]:
            centre[v] = sum(fixed[v]) / 2
        else:
            cl = clusters(v)
            centre[v] = cl[0][1] if cl and len(years[v]) >= 5 else None

    def neighbours(v: str) -> tuple[float | None, float | None]:
        i = order.index(v)
        before = next((centre[u] for u in reversed(order[:i]) if centre[u] is not None), None)
        after = next((centre[u] for u in order[i + 1:] if centre[u] is not None), None)
        return before, after

    for _ in range(3):      # a wrong first guess next door settles within a few rounds
        for v in order:
            if fixed[v] or centre[v] is None:
                continue
            before, after = neighbours(v)
            lo = (before if before is not None else -1e9) - 8
            hi = (after if after is not None else 1e9) + 8
            fits = [(n, c) for n, c in clusters(v) if lo <= c <= hi]
            if fits:
                centre[v] = fits[0][1]

    report = []
    for v, es in by_vol.items():
        span = fixed[v]
        src = "bekannt" if isinstance(known.get(v), dict) else "Titel"
        if not span and centre[v] is not None:
            before, after = neighbours(v) if v in order else (None, None)
            # believable: near the centre, or between the neighbouring volumes' centres
            near = [y for y in years[v] if abs(y - centre[v]) <= 2 * WINDOW
                    or (before is not None and after is not None and before - 1 <= y <= after + 1)]
            span, src = (min(near), max(near)), "gelesene Jahre und Nachbarbände"
            slip = lambda y: any(span[0] <= y + d <= span[1] for d in SLIPS)  # noqa: E731
            few = max(3, len(years[v]) // 10)
            if v in order and v == order[-1]:       # nothing follows the last volume: it may run on
                later = [y for y in years[v] if y > span[1] and not slip(y)]
                if len(later) >= few:
                    span = (span[0], max(later))
            if v in order and v == order[0]:        # nor does anything precede the first
                earlier = [y for y in years[v] if span[0] - 15 <= y < span[0] and not slip(y)]
                if len(earlier) >= few:
                    span = (min(earlier), span[1])
        last, moved, dropped = None, 0, 0
        whose = known[v].get("quelle", "Katalog") if isinstance(known.get(v), dict) else ("Titel des Bandes" if fixed[v] else "erschlossene Spanne")
        for e in es:
            if not e["x"]:
                continue
            e["year_note"] = ""
            y, source = year_of(e["x"]["datum"]), "genannt"
            read = y
            if y and span and not (span[0] - 1 <= y <= span[1] + 1):
                alt = next((y + d for d in SLIPS if span[0] <= y + d <= span[1]), None)
                if alt is None:     # one misread tens digit (1618 for 1658), only if exactly one fits
                    tens = [y - (y // 10 % 10) * 10 + k * 10 for k in range(10)]
                    tens = [x for x in tens if x != y and span[0] <= x <= span[1]]
                    alt = tens[0] if len(tens) == 1 else None
                    kind = "Zehnerziffer"
                else:
                    kind = "50/100 Jahre"
                if alt:
                    y, source, moved = alt, "berichtigt (gelesen als %d)" % y, moved + 1
                else:
                    y, dropped = None, dropped + 1
                # a note wherever the year read and the volume's span disagree (Tobias, 16.11.2026)
                e["year_note"] = (f"Datierung stimmt nicht mit der Laufzeit des Bandes überein: im Text gelesen "
                                  f"«{e['x']['datum_text'] or read}» ({read}), Laufzeit {span[0]}–{span[1]} ({whose}). "
                                  + (f"Jahr berichtigt zu {alt} ({kind})." if alt else "Jahr verworfen, das des vorangehenden Eintrags übernommen."))
            if y and (span or len(years[v]) < 5):
                e["year"], e["year_source"], last = y, source, y
            elif last:
                e["year"], e["year_source"] = last, "vom vorangehenden Eintrag"
            else:
                e["year"], e["year_source"] = None, ""
        inside = [y for y in years[v] if span and span[0] - 1 <= y <= span[1] + 1]
        e0 = es[0]
        e0.setdefault("_vol", {})
        e0["_vol"] = {"span": span, "src": src, "whose": whose, "read": len(years[v]), "inside": len(inside),
                      "moved": moved, "dropped": dropped,
                      "outside": collections.Counter(y for y in years[v] if span and not (span[0] - 1 <= y <= span[1] + 1)).most_common(6)}
        report.append(f"  {v}: {len(es)} entries, {sum(1 for e in es if e['x'])} described, span {span} "
                      f"({src if span else '—'}), {moved} years corrected, {dropped} dropped")
    return report


def write_notes(by_vol: dict[str, list[dict]]) -> None:
    """entries/datierung_vermerke.md: where the years read and the volumes'
    spans disagree, volume by volume and entry by entry."""
    order = sorted(by_vol, key=lambda v: (vol_number(v), v))
    out = ["# Vermerke zur Datierung", "",
           "Wo ein im Eintrag gelesenes Jahr nicht in die Laufzeit des Bandes passt (Laufzeit laut Archivkatalog "
           "des Staatsarchivs, laut Titel oder aus den gelesenen Jahren erschlossen). Erzeugt von scripts/entries.py.", "",
           "## Bände", "", "| Band | Laufzeit | Quelle | Jahre gelesen | davon in der Laufzeit | berichtigt | verworfen | häufigste Jahre ausserhalb |",
           "|---|---|---|---|---|---|---|---|"]
    entries_out = []
    for v in order:
        es = by_vol[v]
        info = es[0].get("_vol") or {}
        if not info or not info.get("span"):
            continue
        share = info["inside"] / info["read"] if info["read"] else 1
        flag = " ⚠" if info["read"] >= 5 and share < 0.8 else ""
        out.append(f"| {v}{flag} | {info['span'][0]}–{info['span'][1]} | {info['whose']} | {info['read']} | "
                   f"{info['inside']} ({share:.0%}) | {info['moved']} | {info['dropped']} | "
                   + ", ".join(f"{y} ×{n}" for y, n in info["outside"]) + " |")
        for e in es:
            if e.get("year_note"):
                entries_out.append(f"- [{e['id']}](https://dhbern.github.io/turmbuecher-data/#/e/{e['id']}/1): {e['year_note']}")
    out += ["", "⚠: weniger als 80 % der gelesenen Jahre liegen in der Laufzeit. Das kann an den Lesungen liegen, an "
            "Einträgen, die frühere Vorgänge erzählen, oder an einer Laufzeit, die nicht zum Band passt.", "",
            f"## Einträge ({len(entries_out)})", ""] + entries_out
    (ENT / "datierung_vermerke.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def build(args) -> None:
    entries = entry_list(args.reader)
    ext = {r["id"]: r for r in jsonl(ENT / "extract.jsonl") if "error" not in r and r.get("reader") == args.reader}
    docs = {p["volume"]: p["doc"] for p in pages()}
    by_vol: dict[str, list[dict]] = {}
    labels = {r["id"]: r for r in jsonl(ENT / "labels.jsonl") if "error" not in r}   # the latest line per entry wins
    for e in entries:
        r = ext.get(e["id"])
        e["x"] = clean(r["x"]) if r else None
        e["tax"] = int(r.get("tax") or 1) if r else None
        lab = labels.get(e["id"])
        if e["x"] and lab and int(lab.get("tax") or 1) >= e["tax"]:
            e["x"]["delikte"] = clean({"delikte": lab["delikte"]})["delikte"]
            e["x"]["delikt_vorschlag"] = str(lab.get("vorschlag") or "").strip()
            e["tax"] = int(lab.get("tax") or 1)
        e["model"] = r["model"] if r else ""
        by_vol.setdefault(e["volume"], []).append(e)

    report = volume_years(by_vol, docs)
    write_notes(by_vol)

    ENT.mkdir(exist_ok=True)
    (ROOT / "regests").mkdir(exist_ok=True)
    rec, units, drafts = [], [], []
    for e in entries:
        x = e["x"]
        keys = list(dict.fromkeys(k for k, _, _ in e["spans"]))
        title = make_title(x) if x and x["art"] != "register" else ""
        rec.append({"id": e["id"], "volume": e["volume"], "nr": e["nr"], "kind": (x or {}).get("art") or e["kind"],
                    "spans": e["spans"], "year": e.get("year"), "year_source": e.get("year_source", ""),
                    "title": title, "reader": args.reader, "model": e["model"], "tax": e.get("tax"),
                    "year_note": e.get("year_note", ""), **(x or {})})
        units.append({"id": e["id"], "shelf": e["volume"], "nr": e["nr"], "title": "", "pages": ";".join(keys),
                      "spans": json.dumps(e["spans"], separators=(",", ":"))})
        if x and x["regest"]:
            drafts.append({"id": e["id"], "heading": title, "reader": args.reader, "model": e["model"],
                           "draft": {"regest": x["regest"], "year": e.get("year"), "year_source": e.get("year_source", ""),
                                     "year_note": e.get("year_note", ""),
                                     "date_text": x["datum_text"],
                                     "persons": x["personen"], "offences": x["delikte"], "place": ""}})
    for path, rows in ((ENT / "entries.jsonl", rec), (ROOT / "regests" / "drafts.jsonl", drafts)):
        tmp = path.with_suffix(".part")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(path)
    with (ROOT / "readings" / "units.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(units[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(units)
    old = sum(1 for e in entries if e["x"] and e["tax"] < VERSION)
    print(f"{len(rec)} entries, {len(drafts)} with a regest; vocabulary version {VERSION}"
          + (f", {old} entries still labelled under an older version (run: entries.py relabel)" if old else ""))
    print("\n".join(report))


# ---------- the vocabulary grows ----------
REL_SYSTEM = """Du prüfst die Delikt-Zuordnung eines Eintrags aus einem Berner Turmbuch (Verhörprotokolle der Berner Obrigkeit, 16.–18. Jahrhundert, frühneuhochdeutsch, maschinell gelesen mit Lesefehlern). Das Vokabular ist um Kategorien erweitert worden.

Du bekommst den Eintrag, die BISHERIGE Zuordnung und die NEUEN Kategorien. Behalte die bisherige Zuordnung bei. Ändere sie nur, wo eine neue Kategorie einen Vorwurf des Eintrags trifft: Füge sie hinzu, und nimm "sonstiges", "unklar" oder eine bisherige Kategorie nur dann heraus, wenn die neue genau diesen Vorwurf besser bezeichnet. Höchstens 4 Delikte, der wichtigste Vorwurf zuerst.

Antworte nur mit JSON: {"delikte": [Kennungen aus der Liste], "vorschlag": nur wenn weiterhin kein Delikt der Liste passt ("sonstiges"): eine kurze heutige Bezeichnung für die fehlende Kategorie, sonst null}

ALLE DELIKTE:
%s""" % "\n".join(f"- {d['id']}: {d['label']} ({d['hinweis']})" for d in TAX["delikte"])


def relabel(args) -> None:
    """Offences again for entries labelled under an older vocabulary version:
    the model sees the labels the entry has and the categories added since
    (``seit`` in taxonomy/delikte.json), and is told to change nothing else.
    One short call per entry; dates, persons and regests are not redone."""
    lines = page_lines(args.reader)
    want = {p["volume"] for p in selected(args)}
    ext = {r["id"]: r for r in jsonl(ENT / "extract.jsonl") if "error" not in r and r.get("reader") == args.reader}
    labels = {r["id"]: r for r in jsonl(ENT / "labels.jsonl") if "error" not in r}
    log = Log(ENT / "labels.jsonl", "id")
    todo = []
    for e in entry_list(args.reader):
        r = ext.get(e["id"])
        if not r or e["volume"] not in want:
            continue
        lab = labels.get(e["id"])
        e["at"] = max(int(r.get("tax") or 1), int(lab.get("tax") or 1) if lab else 0)
        e["now"] = clean({"delikte": (lab or {}).get("delikte") if lab and int(lab.get("tax") or 1) >= int(r.get("tax") or 1)
                          else (r["x"].get("delikte") if isinstance(r.get("x"), dict) else [])})["delikte"]
        if not e["now"]:            # no offence so far (a register, a note): nothing to extend
            continue
        if e["at"] < VERSION or args.force:
            todo.append(e)

    def work(e: dict) -> None:
        new = [d for d in TAX["delikte"] if int(d.get("seit") or 1) > e["at"]] or TAX["delikte"]
        text = entry_text(e, lines)
        if len(text) > MAX_HEAD + MAX_TAIL:
            text = text[:MAX_HEAD] + "\n[…]\n" + text[-MAX_TAIL:]
        user = ("BISHERIGE Zuordnung: " + json.dumps(e["now"], ensure_ascii=False) + "\nNEUE Kategorien: " +
                "; ".join(f"{d['id']} ({d['label']}: {d['hinweis']})" for d in new) + f"\n\nEINTRAG:\n{text}")
        ans = llm.parse_json(llm.chat(REL_SYSTEM, user, 200))
        log.add({"id": e["id"], "delikte": ans.get("delikte") if isinstance(ans.get("delikte"), list) else e["now"],
                 "vorschlag": ans.get("vorschlag"), "tax": VERSION, "model": llm.MODEL})

    print(f"vocabulary version {VERSION}: {len(todo)} entries to label again")
    run(todo, work, "relabel")


def vorschlaege(args) -> None:
    """entries/vorschlaege.tsv: the entries no category fits, grouped by what
    the model would have called them."""
    rows = [e for e in jsonl(ENT / "entries.jsonl") if set(e.get("delikte") or []) & {"sonstiges", "unklar"}]
    groups: dict[str, list[dict]] = {}
    for e in rows:
        groups.setdefault((e.get("delikt_vorschlag") or "").strip().lower() or "(kein Vorschlag)", []).append(e)
    path = ENT / "vorschlaege.tsv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["vorschlag", "eintraege", "beispiele", "woertlich"])
        for k, es in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            w.writerow([k, len(es), " ".join(e["id"] for e in es[:5]),
                        " | ".join(dict.fromkeys(e.get("delikt_woertlich", "")[:80] for e in es if e.get("delikt_woertlich")))[:400]])
    print(f"{len(rows)} entries without a fitting category, {len(groups)} proposals → {path.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["segment", "extract", "build", "relabel", "vorschlaege"])
    ap.add_argument("--volumes", default="")
    ap.add_argument("--reader", default="transkribus-bestand")
    ap.add_argument("--force", action="store_true", help="relabel: also entries already labelled under the current version")
    args = ap.parse_args()
    {"segment": segment, "extract": extract, "build": build, "relabel": relabel, "vorschlaege": vorschlaege}[args.step](args)


if __name__ == "__main__":
    main()

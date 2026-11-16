"""TEI for the Turmbücher: one file per volume.

    python scripts/tei_export.py [--out site/data/tei] [--volumes "B IX 467"]

Each file holds a volume's entries as ``<div type="eintrag">``:

* the text as it stands in Transkribus, line by line (``<lb facs="#zone">``),
  with the persons, places, organisations and dates tagged there
  (``resp="#transkribus"``), and, where the joint reading changed a word,
  ``<choice><orig>`` (Transkribus) ``<reg resp="#lesungen">`` (the word two other
  readers agree on);
* the machine's description: title (``<head>``), regest, date, the offences,
  procedure and outcome as pointers into the vocabulary in the header
  (``@ana``), the persons with their role and the places, with authority
  identifiers where the registers propose one (``@cert``);
* ``<facsimile>``: a ``<surface>`` per page with the image on the Transkribus
  IIIF server and a ``<zone>`` per line (its bounding box in pixels).

Everything a machine produced carries ``@resp`` pointing to it and ``@cert``.
Nothing here is an edited text: the header says so (``<editorialDecl>``).
Editors and contributors come from ``taxonomy/verantwortliche.json``.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import register as reg  # noqa: E402

IIIF = "https://files.transkribus.eu/iiif/2/"
SITE = "https://dhbern.github.io/turmbuecher-data/"
TAG = {"per": "persName", "place": "placeName", "org": "orgName", "date": "date"}
TOKEN = re.compile(r"\S+")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def xid(s: str) -> str:
    """An xml:id: letters, digits, '_', '-', '.', starting with a letter."""
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", s)
    return s if re.match(r"[A-Za-z_]", s) else "x" + s


def a(**attrs) -> str:
    return "".join(f" {k.replace('__', ':').rstrip('_')}={quoteattr(str(v))}" for k, v in attrs.items() if v not in (None, ""))


def header(vol: str, doc: str, span, tax: dict, people: dict, models: list[str], today: str) -> str:
    def person(p, tag):
        orcid = f'<idno type="ORCID">https://orcid.org/{p["orcid"]}</idno>' if p.get("orcid") else ""
        inner = f'<persName>{escape(p["name"])}</persName>{orcid}<affiliation>{escape(p["ort"])}</affiliation>'
        return f"<{tag}>{inner}</{tag}>" if tag == "editor" else f"<name type=\"person\">{inner}</name>"

    groups: dict[str, list[dict]] = {}
    for d in tax["delikte"]:
        groups.setdefault(d["gruppe"], []).append(d)
    cats = "".join(
        f'<category xml:id="{xid("grp." + g)}"><catDesc>{escape(g)}</catDesc>' +
        "".join(f'<category xml:id="del.{d["id"]}"><catDesc><term>{escape(d["label"])}</term>{" <gloss>" + escape(d["hinweis"]) + "</gloss>" if d.get("hinweis") else ""}</catDesc></category>' for d in ds) +
        "</category>" for g, ds in groups.items())
    proc = "".join(f'<category xml:id="verf.{d["id"]}"><catDesc>{escape(d["label"])}</catDesc></category>' for d in tax["verfahren"])
    sanc = "".join(f'<category xml:id="san.{d["id"]}"><catDesc>{escape(d["label"])}</catDesc></category>' for d in tax["sanktionen"])
    when = f'<origDate notBefore="{span[0]}" notAfter="{span[1]}">{span[0]}–{span[1]}</origDate>' if span else "<origDate>16.–18. Jahrhundert</origDate>"
    shelf = vol if vol.startswith("B IX") else f"Turmbuch «{vol}» (Signatur nicht erfasst)"
    return f"""<teiHeader>
<fileDesc>
<titleStmt>
<title>Berner Turmbuch {escape(doc if vol.startswith("B IX") else vol)}: maschinelle Lesung und Erschliessung</title>
{"".join(person(p, "editor") for p in people["herausgebende"])}
<respStmt><resp>Mitarbeit im Projekt «The Flow» (flow-project.net)</resp>{"".join(person(p, "name") for p in people["mitarbeitende"])}</respStmt>
<respStmt xml:id="transkribus"><resp>Text, Zeilen und Auszeichnungen aus der Transkribus-Sammlung 187323 «StABE_Turmbücher_DH_flow»: automatische Texterkennung, auf einem Teil der Seiten von Hand korrigiert (Projekt «The Flow»)</resp><name type="software">Transkribus</name></respStmt>
<respStmt xml:id="erschliessung"><resp>Eintragsgrenzen, Datum, Titel, Regest, Personen, Orte, Delikte, Verfahren und Ausgang: maschinell erzeugt, ungeprüft</resp>{"".join(f'<name type="model">{escape(m)}</name>' for m in models) or '<name type="model">Sprachmodell</name>'}</respStmt>
<respStmt xml:id="lesungen"><resp>Wörter, in denen zwei weitere maschinelle Lesungen übereinstimmend vom Transkribus-Text abweichen (scripts/joint_reading.py)</resp><name type="model">qwen3.5-4b-german-kurrent-xvi-xix-page-v1</name><name type="model">trocr-kurrent-xvi-xvii</name></respStmt>
<respStmt xml:id="register"><resp>Verknüpfung mit Normdaten nach Regeln (scripts/register.py, scripts/places.py): Vorschläge, ungeprüft</resp><name type="software">turmbuecher-data</name></respStmt>
<funder>Schweizerischer Nationalfonds (SNF)</funder>
<funder>Deutsche Forschungsgemeinschaft (DFG)</funder>
</titleStmt>
<publicationStmt>
<publisher>Digital Humanities, Universität Bern</publisher>
<date when="{today}">{today}</date>
<idno type="URI">{SITE}</idno>
<availability><licence target="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0. Die Bilder der Vorlage sind gemeinfrei (Staatsarchiv des Kantons Bern).</licence></availability>
</publicationStmt>
<sourceDesc><msDesc><msIdentifier><settlement>Bern</settlement><repository>Staatsarchiv des Kantons Bern (StABE)</repository><idno>{escape(shelf)}</idno></msIdentifier>
<msContents><summary>Turmbuch: Verhöre, Geständnisse und Urteile der Berner Obrigkeit.</summary></msContents>
<history><origin>{when}</origin></history></msDesc></sourceDesc>
</fileDesc>
<encodingDesc>
<projectDesc><p>Prototyp für die Suche in den Berner Turmbüchern und ihre inhaltliche Erschliessung, hervorgegangen aus dem Projekt «The Flow» (SNF/DFG, 2023–2026).</p></projectDesc>
<editorialDecl><p>Kein edierter Text. Der Text ist der Stand der Transkribus-Sammlung: Seiten, deren <gi>surface</gi> den Typ <val>ground-truth</val> trägt, sind dort als Ground Truth markiert; alle übrigen sind unkorrigierte Maschinenlesung. Die Gliederung in Einträge und alles, was <att>resp</att> auf <val>#erschliessung</val> verweist, hat ein Sprachmodell erzeugt; niemand hat es geprüft. Jahre gelten nur innerhalb der Spanne des Bandes; <att>cert</att> an <gi>date</gi> sagt, ob das Jahr im Eintrag genannt (<val>medium</val>), berichtigt oder vom vorangehenden Eintrag übernommen ist (<val>low</val>). Normdaten-Kennungen sind Vorschläge.</p></editorialDecl>
<classDecl>
<taxonomy xml:id="delikte" n="{tax.get("version", 1)}"><bibl>Deliktvokabular des Prototyps, Version {tax.get("version", 1)} (taxonomy/delikte.json), erweiterbar</bibl>{cats}</taxonomy>
<taxonomy xml:id="verfahren"><bibl>Verfahren</bibl>{proc}</taxonomy>
<taxonomy xml:id="sanktionen"><bibl>Ausgang</bibl>{sanc}</taxonomy>
</classDecl>
</encodingDesc>
<profileDesc><langUsage><language ident="gmh-x-fnhd">Frühneuhochdeutsch</language><language ident="de">Deutsch (Titel, Regesten)</language></langUsage></profileDesc>
</teiHeader>"""


def mark_line(text: str, ents: list[tuple[int, int, str]], changes: list[dict]) -> str:
    """One line as TEI content: the Transkribus tags, and <choice> where the
    joint reading replaced a word (only if that word occurs once in the line
    and no tag touches it)."""
    spans = sorted((s, e, f"<{TAG[t]} resp=\"#transkribus\">", f"</{TAG[t]}>") for s, e, t in ents if t in TAG and e > s)
    kept, last = [], 0
    for s, e, o, c in spans:        # tags that overlap an earlier one are dropped
        if s >= last:
            kept.append((s, e, o, c))
            last = e
    for ch in changes:
        hits = [m for m in TOKEN.finditer(text) if m.group() == ch["from"]]
        if len(hits) == 1 and not any(s < hits[0].end() and hits[0].start() < e for s, e, _, _ in kept):
            m = hits[0]
            kept.append((m.start(), m.end(), "<choice><orig>", f"</orig><reg resp=\"#lesungen\">{escape(ch['to'])}</reg></choice>"))
    out, at = "", 0
    for s, e, o, c in sorted(kept):
        if s < at:
            continue
        out += escape(text[at:s]) + o + escape(text[s:e]) + c
        at = e
    return out + escape(text[at:])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "tei")
    ap.add_argument("--volumes", default="")
    args = ap.parse_args()
    today = datetime.date.today().isoformat()
    tax = json.loads((ROOT / "taxonomy" / "delikte.json").read_text(encoding="utf-8"))
    people = json.loads((ROOT / "taxonomy" / "verantwortliche.json").read_text(encoding="utf-8"))
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        pages = {r["key"]: r for r in csv.DictReader(fh, delimiter="\t")}
    text = {r["key"]: r["text"].split("\n") for r in jsonl(ROOT / "readings" / "transkribus-bestand.jsonl")}
    ents = {r["key"]: r["entities"] for r in jsonl(ROOT / "entities" / "transkribus-bestand.jsonl")}
    joint = {r["key"]: r for r in jsonl(ROOT / "readings" / "joint.jsonl") if r.get("backbone") == "transkribus-bestand"}
    entries = jsonl(ROOT / "entries" / "entries.jsonl")
    want = [v.strip() for v in args.volumes.split(",") if v.strip()]

    # registers: place by the name an entry uses; HLS proposal by (entry, name form)
    orte = json.loads((ROOT / "register" / "orte.json").read_text(encoding="utf-8")) if (ROOT / "register" / "orte.json").exists() else {"places": []}
    place_of = {n: p for p in orte["places"] for n in p["names"]}
    hls_of: dict[tuple[str, str], dict] = {}
    pers_path = ROOT / "register" / "personen.json"
    for r in json.loads(pers_path.read_text(encoding="utf-8"))["persons"] if pers_path.exists() else []:
        for h in r.get("hls") or []:
            for eid in h["entries"]:
                if h["grade"] == "wahrscheinlich" or (eid, r["key"]) not in hls_of:
                    hls_of[(eid, r["key"])] = h

    by_vol: dict[str, list[dict]] = {}
    for e in entries:
        by_vol.setdefault(e["volume"], []).append(e)
    args.out.mkdir(parents=True, exist_ok=True)
    index, stats = [], {"entries": 0, "choices": 0}
    for vol, es in by_vol.items():
        if want and vol not in want:
            continue
        geo = {r["key"]: r for r in jsonl(ROOT / "readings" / "lines" / (re.sub(r"[^A-Za-z0-9]+", "_", vol) + ".jsonl"))}
        keys = list(dict.fromkeys(k for e in es for k, _, _ in e["spans"]))
        doc = pages[keys[0]]["doc"]
        years = [e["year"] for e in es if e.get("year")]
        span = (min(years), max(years)) if years else None
        models = sorted({e["model"] for e in es if e.get("model")})

        # facsimile: a surface per page, a zone per line that has text and an outline
        zone_of: dict[tuple[str, int], str] = {}
        fac = []
        for k in keys:
            p = pages[k]
            w, h = int(p["width"] or 0), int(p["height"] or 0)
            zones = ""
            g = geo.get(k)
            if g and w:
                rows = [(poly, t) for poly, t in zip(g["poly"], g["text"]) if t.strip()]
                if [t for _, t in rows] == text.get(k):
                    for i, (poly, _) in enumerate(rows):
                        xs, ys = poly[0::2], poly[1::2]
                        f = w / 1e4
                        zid = f"{xid(k)}_l{i + 1}"
                        zone_of[(k, i)] = zid
                        zones += f'<zone xml:id="{zid}" ulx="{round(min(xs) * f)}" uly="{round(min(ys) * f)}" lrx="{round(max(xs) * f)}" lry="{round(max(ys) * f)}"/>'
            typ = "ground-truth" if p["status"] in ("GT", "DONE", "FINAL") else "maschinenlesung"
            fac.append(f'<surface xml:id="{xid(k)}" n="{p["pageNr"]}" type="{typ}"{a(ulx=0, uly=0, lrx=w or None, lry=h or None)}>'
                       f'<graphic url="{IIIF}{p["tk"]}/full/max/0/default.jpg"/>{zones}</surface>')

        divs = []
        for e in es:
            stats["entries"] += 1
            ana = " ".join([f"#del.{o}" for o in e.get("delikte") or []] + [f"#verf.{o}" for o in e.get("verfahren") or []] +
                           [f"#san.{o}" for o in e.get("sanktionen") or []])
            d = [f'<div type="eintrag" xml:id="{xid(e["id"])}" n="{e["nr"]}"{a(ana=ana, subtype=e.get("kind"))}>']
            if e.get("title"):
                d.append(f'<head type="titel" resp="#erschliessung" cert="low">{escape(e["title"])}</head>')
            if e.get("year") or e.get("datum_text"):
                src = e.get("year_source", "")
                cert = "medium" if src == "genannt" else "low"
                d.append(f'<note type="datierung" resp="#erschliessung"><date{a(when=e.get("year"), cert=cert)}>{escape(e.get("datum_text") or str(e.get("year")))}</date>'
                         f'{" (Jahr: " + escape(src) + ")" if src else ""}</note>')
            if e.get("year_note"):
                d.append(f'<note type="vermerk" subtype="datierung" resp="#erschliessung">{escape(e["year_note"])}</note>')
            if e.get("regest"):
                d.append(f'<note type="regest" resp="#erschliessung" xml:lang="de">{escape(e["regest"])}</note>')
            if e.get("delikt_woertlich"):
                d.append(f'<note type="vorwurf" resp="#erschliessung"><quote>{escape(e["delikt_woertlich"])}</quote></note>')
            if e.get("personen"):
                ps = []
                for p in e["personen"]:
                    h = hls_of.get((e["id"], reg.name_key(p["name"])[0]))
                    ids = ""
                    if h:
                        c = "medium" if h["grade"] == "wahrscheinlich" else "low"
                        ids = (f'<idno type="HLS" cert="{c}" resp="#register">{h["hls"]}</idno><idno type="Wikidata" cert="{c}" resp="#register">{h["qid"]}</idno>' +
                               (f'<idno type="GND" cert="{c}" resp="#register">{h["gnd"]}</idno>' if h.get("gnd") else "") +
                               (f'<idno type="SSRQ" cert="{c}" resp="#register">{h["ssrq"]["id"]}</idno>' if h.get("ssrq") else ""))
                    sex = {"m": "M", "w": "F"}.get(p.get("geschlecht"))
                    ps.append(f'<person{a(role=p["rolle"], sex=sex)}><persName>{escape(p["name"])}</persName>{ids}'
                              f'{"<residence>" + escape(p["herkunft"]) + "</residence>" if p.get("herkunft") else ""}</person>')
                d.append(f'<listPerson resp="#erschliessung">{"".join(ps)}</listPerson>')
            if e.get("orte"):
                pl = []
                for o in e["orte"]:
                    p = place_of.get(o.strip())
                    extra = ""
                    if p:
                        links = p.get("links") or {}
                        extra = (f'<placeName type="normalisiert" resp="#register" cert="low">{escape(p["name"])}</placeName>'
                                 f'<location resp="#register" cert="low"><geo>{p["lat"]} {p["lon"]}</geo></location>' +
                                 "".join(f'<idno type="{t}" resp="#register">{links[k]}</idno>' for k, t in (("hls", "HLS"), ("qid", "Wikidata"), ("gnd", "GND"), ("geonames", "GeoNames"), ("bfs", "BFS")) if links.get(k)))
                    pl.append(f"<place><placeName>{escape(o)}</placeName>{extra}</place>")
                d.append(f'<listPlace resp="#erschliessung">{"".join(pl)}</listPlace>')
            body = []
            for key, first, last in e["spans"]:
                lines = text.get(key) or []
                body.append(f'<pb n="{pages[key]["pageNr"]}" facs="#{xid(key)}"/>')
                starts, at = [], 0
                for ln in lines:
                    starts.append(at)
                    at += len(ln) + 1
                ch_by = {}
                for c in (joint.get(key) or {}).get("changes") or []:
                    ch_by.setdefault(c["line"], []).append(c)
                for i in range(first, min(last, len(lines) - 1) + 1):
                    le = [(x["start"] - starts[i], x["end"] - starts[i], x["type"]) for x in ents.get(key) or []
                          if starts[i] <= x["start"] and x["end"] <= starts[i] + len(lines[i])]
                    marked = mark_line(lines[i], le, ch_by.get(i, []))
                    stats["choices"] += marked.count("<choice>")
                    z = zone_of.get((key, i))
                    body.append(f'<lb n="{i + 1}"{a(facs="#" + z if z else None)}/>{marked}')
            d.append(f'<ab type="text" resp="#transkribus">{chr(10).join(body)}</ab>' if body else "<ab/>")
            d.append("</div>")
            divs.append("\n".join(d))

        name = re.sub(r"[^A-Za-z0-9]+", "_", vol) + ".xml"
        xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="{xid(name[:-4])}">\n' +
               header(vol, doc, span, tax, people, models, today) +
               f'\n<facsimile>\n{chr(10).join(fac)}\n</facsimile>\n<text><body>\n' + "\n".join(divs) + "\n</body></text>\n</TEI>\n")
        tmp = args.out / (name + ".part")
        tmp.write_text(xml, encoding="utf-8")
        tmp.replace(args.out / name)
        index.append({"volume": vol, "file": name, "entries": len(es), "pages": len(keys), "bytes": len(xml.encode())})
    (args.out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index)} volumes, {stats['entries']} entries, {stats['choices']} words with a joint reading; "
          f"{sum(x['bytes'] for x in index) / 1e6:.0f} MB in {args.out}")


if __name__ == "__main__":
    main()

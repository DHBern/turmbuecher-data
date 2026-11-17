"""Import the text that stands in Transkribus as the first reading of the Turmbücher.

    python scripts/import_transkribus.py <manifest.jsonl> <pagexml dir>

Inputs (written by ``ops/ingest_transkribus.py`` on tei; neither is committed):

* ``manifest.jsonl``: one row per page of Transkribus collection 187323 with
  ``key``, ``doc``, ``pageNr``, ``width``, ``height``, ``tk``, ``status``,
  ``lines``, ``transcribed_lines``;
* ``pagexml/<key>.xml``: the latest transcript of that page.

Outputs:

* ``readings/pages.tsv``: every page, in shelfmark order: key, volume, page,
  size, Transkribus status, lines, lines with text, image identifier. This
  file defines the pages the viewer knows.
* ``readings/transkribus-bestand.jsonl``: one line per page that has text,
  ``{"key", "text"}``, one text line per ``TextLine`` that has text, in reading
  order, trailing blanks removed.
* ``readings/lines/<volume>.jsonl``: the line geometry of every page with ``TextLine``s:
  ``{"key", "size": [w, h], "poly": [[x, y, ...], ...], "text": [...],
  "region": [...]}`` — per ``TextLine`` its outline (at most ``POLY_POINTS``
  points, in ten-thousandths of the image *width*, the unit OpenSeadragon
  places overlays in), its text, and the structure type of its region
  (``heading``, ``paragraph``, ``page-number``, ``marginalia`` … or ``""``).
* ``entities/transkribus-bestand.jsonl``: the tags that stand on the lines in
  Transkribus (``person``, ``place``, ``organization``, ``date``), as character
  spans of the page text: ``{"key", "entities": [{"start", "end", "type",
  "text"}]}``. Who or what set these tags is not recorded in Transkribus.

Only machine readings are published until the Ground Truth appears on 1 July
2027 (``readings/vorbehalt.tsv``, written by ``scripts/vorbehalt.py``): where a
page's text is Ground Truth or corrected by hand, the newest HTR version of the
page is read instead (``_ingest/pagexml_public/<key>.xml``) or, without one, the
page keeps its lines but no text; a page empty here takes over the machine
reading of an older collection. Pages with Ground Truth anywhere get the status
``GT`` in ``pages.tsv``.

Nothing personal is carried over (the manifest holds no user names; the check
below fails the run if an e-mail address would end up in an output file).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
READER = "transkribus-bestand"
POLY_POINTS = 12
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RO = re.compile(r"readingOrder\s*\{\s*index:\s*(\d+)")
STRUCT = re.compile(r"structure\s*\{[^}]*type:\s*([^;}]+)")
TAG = re.compile(r"(\w+)\s*\{([^}]*)\}")
TAG_TYPES = {"person": "per", "place": "place", "organization": "org", "date": "date"}


def doc_sort_key(title: str) -> tuple:
    """'B IX 422' … 'B IX 509' by number; anything else last, alphabetically."""
    m = re.match(r"^B IX (\d+)", title)
    return (0, int(m.group(1)), title) if m else (1, 0, title)


def volume(title: str) -> str:
    """'B IX 428 (1564-1566)' -> 'B IX 428'; 'B IX 498 (neu)' -> 'B IX 498'."""
    if title.startswith("Henzi"):       # "Henzi_duplicated": a document name from the making, one volume
        return "Henzi"
    return re.sub(r"\s*\(.*?\)\s*", "", title).strip()


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def ro_index(el, default: int) -> int:
    m = RO.search(el.get("custom") or "")
    return int(m.group(1)) if m else default


def line_text(tl) -> str:
    """The TextLine's own TextEquiv (not its Words'), the lowest @index."""
    equivs = [e for e in tl if local(e) == "TextEquiv"]
    if not equivs:
        return ""
    best = min(equivs, key=lambda e: int(e.get("index") or 0))
    uni = next((u for u in best if local(u) == "Unicode"), None)
    return "".join(uni.itertext()) if uni is not None else ""


def points(el) -> list[tuple[int, int]]:
    c = next((e for e in el if local(e) == "Coords"), None)
    out = []
    for xy in (c.get("points") or "").split() if c is not None else []:
        try:
            x, y = xy.split(",")
            out.append((int(float(x)), int(float(y))))
        except ValueError:
            continue
    return out


def _seg_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def _dp(pts: list, tol: float) -> list:
    if len(pts) < 3:
        return pts
    d, i = max((_seg_dist(p, pts[0], pts[-1]), k) for k, p in enumerate(pts[1:-1], 1))
    if d <= tol:
        return [pts[0], pts[-1]]
    return _dp(pts[: i + 1], tol)[:-1] + _dp(pts[i:], tol)


def _area(pts: list) -> float:
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2


def simplify(pts: list[tuple[int, int]], most: int = POLY_POINTS) -> list[tuple[int, int]]:
    """The closed outline with at most ``most`` points: Douglas–Peucker on the
    two halves between the first point and the one farthest from it, with a
    growing tolerance. An outline that loses more than a quarter of its area
    that way (a thin line collapsing to a sliver) becomes its bounding box."""
    if len(pts) <= most:
        return pts
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    tol, out = 1.0, pts
    while len(out) > most and tol < 4096:
        out = _dp(pts[: far + 1], tol)[:-1] + _dp(pts[far:] + pts[:1], tol)[:-1]
        tol *= 1.5
    full = _area(pts)
    if len(out) < 4 or len(out) > most or (full and abs(_area(out) - full) / full > 0.25):
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    return out


def tags(custom: str) -> list[tuple[str, int, int]]:
    """(type, offset, length) of every person/place/organization/date tag of a line."""
    out = []
    for name, body in TAG.findall(custom or ""):
        if name not in TAG_TYPES:
            continue
        o, n = re.search(r"offset:\s*(\d+)", body), re.search(r"length:\s*(\d+)", body)
        if o and n and int(n.group(1)) > 0:
            out.append((TAG_TYPES[name], int(o.group(1)), int(n.group(1))))
    return out


def read_page(path: Path) -> tuple[list[dict], tuple[int, int]]:
    """Every TextLine in reading order — regions by the ReadingOrder (else
    document order), lines by their readingOrder index — with its text, outline,
    region structure type and tags."""
    root = etree.parse(str(path), etree.XMLParser(recover=True)).getroot()
    page = next((el for el in root.iter() if local(el) == "Page"), None)
    size = (int(page.get("imageWidth") or 0), int(page.get("imageHeight") or 0)) if page is not None else (0, 0)
    regions = [el for el in root.iter() if local(el) == "TextRegion"]
    by_id = {r.get("id"): r for r in regions}
    refs = sorted((int(el.get("index") or 0), el.get("regionRef"))
                  for el in root.iter() if local(el) == "RegionRefIndexed")
    ordered = [by_id[r] for _, r in refs if r in by_id]
    ordered += [r for r in regions if r not in ordered]
    lines = []
    for region in ordered:
        m = STRUCT.search(region.get("custom") or "")
        rtype = (m.group(1).strip() if m else "") or (region.get("type") or "")
        tls = [tl for tl in region if local(tl) == "TextLine"]
        for _, tl in sorted(enumerate(tls), key=lambda p: ro_index(p[1], p[0])):
            lines.append({"id": tl.get("id"), "text": line_text(tl), "coords": points(tl), "region": rtype,
                          "tags": tags(tl.get("custom") or "")})
    return lines, size


def geometry(key: str, lines: list[dict], size: tuple[int, int]) -> dict | None:
    w, h = size
    if not w or not h:
        return None
    k = 1e4 / w
    poly, text, region = [], [], []
    for x in lines:
        pts = [(min(max(px, 0), w), min(max(py, 0), h)) for px, py in x["coords"]]
        if len(pts) < 3:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(xs) == min(xs) or max(ys) == min(ys):
            continue
        poly.append([round(v * k) for p in simplify(pts) for v in p])
        text.append(x["text"].rstrip())
        region.append(x["region"])
    if not poly:
        return None
    return {"key": key, "size": [w, h], "poly": poly, "text": text, "region": region}


def page_text(lines: list[dict]) -> tuple[str, list[dict]]:
    """The page text (lines with text only, right-stripped) and the tags as
    spans of it. A tag reaching past its line's text is cut to the line."""
    out, ents, at = [], [], 0
    for x in lines:
        t = x["text"].rstrip()
        if not t.strip():
            continue
        for typ, off, n in x["tags"]:
            a, b = min(off, len(t)), min(off + n, len(t))
            if b > a and t[a:b].strip():
                ents.append({"start": at + a, "end": at + b, "type": typ, "text": t[a:b]})
        out.append(t)
        at += len(t) + 1
    ents.sort(key=lambda e: (e["start"], -e["end"]))
    return "\n".join(out), ents


def check_public(paths: list[Path]) -> None:
    for p in paths:
        s = p.read_text(encoding="utf-8")
        if EMAIL.search(s) or "userName" in s or "userId" in s:
            sys.exit(f"{p}: contains an e-mail address or a user field — not written for the public repo")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in rows), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("pagexml", type=Path)
    ap.add_argument("--vorbehalt", type=Path, default=ROOT / "readings" / "vorbehalt.tsv")
    ap.add_argument("--public", type=Path, default=ROOT / "_ingest" / "pagexml_public")
    args = ap.parse_args()
    with args.vorbehalt.open(encoding="utf-8") as fh:
        vb = {r["key"]: r for r in csv.DictReader(fh, delimiter="\t")}

    rows = [json.loads(x) for x in args.manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows.sort(key=lambda r: (doc_sort_key(r["doc"]), int(r["pageNr"])))
    readings, table, geo, entities, missing = [], [], [], [], 0
    for r in rows:
        xml = args.pagexml / f"{r['key']}.xml"
        v = vb.get(r["key"]) or {}
        if v.get("text") in ("htr", "andere-sammlung"):
            xml = args.public / f"{r['key']}.xml"
        text, ents, n_text = "", [], 0
        if xml.exists():
            lines, size = read_page(xml)
            if v.get("text") == "keiner":          # Ground Truth or hand-made, no machine version: lines only
                lines = [dict(x, text="", tags=[]) for x in lines]
            text, ents = page_text(lines)
            n_text = len(text.split("\n")) if text else 0
            g = geometry(r["key"], lines, size)
            if g:
                geo.append(g)
        else:
            missing += 1
        table.append({"key": r["key"], "volume": volume(r["doc"]), "doc": r["doc"], "docId": r["docId"],
                      "pageNr": int(r["pageNr"]), "width": r.get("width") or "", "height": r.get("height") or "",
                      "status": "GT" if v.get("ground_truth") else (r.get("status") or ""), "lines": r.get("lines") or 0, "text_lines": n_text,
                      "tk": r.get("tk") or ""})
        if text:
            readings.append({"key": r["key"], "text": text})
        if ents:
            entities.append({"key": r["key"], "entities": ents})

    (ROOT / "readings").mkdir(exist_ok=True)
    (ROOT / "entities").mkdir(exist_ok=True)
    # line geometry: one file per volume (readings/lines/<volume>.jsonl), the
    # whole corpus in one file would pass GitHub's size limit
    (ROOT / "readings" / "lines").mkdir(exist_ok=True)
    vol_of = {r["key"]: r["volume"] for r in table}
    by_vol: dict[str, list[dict]] = {}
    for g in geo:
        by_vol.setdefault(vol_of[g["key"]], []).append(g)
    line_files = []
    for v, rows_v in by_vol.items():
        path = ROOT / "readings" / "lines" / (re.sub(r"[^A-Za-z0-9]+", "_", v) + ".jsonl")
        write_jsonl(path, rows_v)
        line_files.append(path)
    out = [ROOT / "readings" / f"{READER}.jsonl", ROOT / "entities" / f"{READER}.jsonl",
           ROOT / "readings" / "pages.tsv"] + line_files
    write_jsonl(out[0], readings)
    write_jsonl(out[1], entities)
    with out[2].open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(table)
    check_public(out)
    by = {}
    for e in entities:
        for x in e["entities"]:
            by[x["type"]] = by.get(x["type"], 0) + 1
    print(f"{len(table)} pages in {len({r['volume'] for r in table})} volumes; {len(readings)} with text; "
          f"{len(geo)} with line geometry ({sum(len(g['poly']) for g in geo)} lines); "
          f"tags {by}; {missing} without PAGE XML")


if __name__ == "__main__":
    main()

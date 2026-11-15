"""Places of the entries, with coordinates: the data behind the map.

    python scripts/places.py geocode [--min 2]     # ask swisstopo, cached
    python scripts/places.py build                 # → register/orte.json

Place names come from the entries (``entries/entries.jsonl``): the places an
entry names (``orte``) and where the accused are from (``herkunft``), as the
language model wrote them. They are looked up in swisstopo's public place
search (api3.geo.admin.ch SearchServer: municipalities ``gg25`` and settlement
names from the ``gazetteer``), after ``taxonomy/ortsnamen.json`` has turned
older German names into today's. Only places in Switzerland can be found this
way; regions and countries are not points and stay off the map.

A name is linked only when the match is by the **whole name** and

1. exactly one municipality bears it (``Gemeinde``) — unless it lies outside
   the canton of Bern and a Bernese municipality bears the name with an
   official addition («Büren» SO against «Büren an der Aare»): then
2. the one Bernese municipality among several candidates is taken
   (``mehrdeutig, Kanton Bern bevorzugt``; with the addition alone: ``Name mit
   Zusatz``), or the one in the old Bernese territory (BE, AG, VD); two
   Bernese candidates stay unlinked; or
3. no municipality but exactly one settlement bears it, or exactly one in the
   canton of Bern (``Siedlung``).

Everything else stays unlinked rather than guessed. A link is a machine's
proposal on a name a machine read: the register says which rule made it.
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "register"
CACHE = REG / "orte_cache.jsonl"
API = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
BERNESE = ("BE", "AG", "VD")
# The interrogations took place in the tower at the Marzili in Bern; the model often
# takes that for where the accused is from. It stays a named place, never an origin.
NOT_AN_ORIGIN = {"Marzili"}
ALIAS = {k: v for k, v in json.loads((ROOT / "taxonomy" / "ortsnamen.json").read_text(encoding="utf-8")).items() if k != "_"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.replace("ß", "ss")).strip()


def mentions() -> tuple[collections.Counter, list[dict]]:
    entries = [json.loads(x) for x in (ROOT / "entries" / "entries.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    entries = [e for e in entries if e.get("regest")]
    n = collections.Counter()
    for e in entries:
        names = set(e.get("orte") or []) | {p["herkunft"] for p in e.get("personen") or [] if p.get("herkunft")}
        for x in names:
            n[x.strip()] += 1
    return n, entries


def search(name: str) -> list[dict]:
    q = urllib.parse.urlencode({"searchText": name, "type": "locations", "origins": "gg25,gazetteer", "sr": "4326", "limit": "30"})
    err = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "turmbuecher-places"}), timeout=30) as r:
                res = json.loads(r.read()).get("results") or []
            break
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:100]
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(err)
    out = []
    for x in res:
        a = x.get("attrs") or {}
        label = html.unescape(a.get("label") or "")
        kind = (re.search(r"<i>(.*?)</i>", label) or [None, ""])[1]
        bold = (re.search(r"<b>(.*?)</b>", label) or [None, ""])[1]
        canton = (re.search(r"\(([A-Z]{2})\)", label) or [None, ""])[1]
        if a.get("origin") == "gazetteer" and a.get("objectclass") != "TLM_SIEDLUNGSNAME":
            continue        # buildings, field names, summits: not what a Turmbuch means by a place
        out.append({"origin": a.get("origin"), "name": re.sub(r"\s*\([A-Z]{2}\)\s*$", "", bold).strip(), "label": re.sub(r"<.*?>", "", label),
                    "canton": canton, "kind": kind, "lat": a.get("lat"), "lon": a.get("lon"), "id": a.get("featureId")})
    return out


def cache() -> dict[str, list[dict]]:
    out = {}
    for line in CACHE.read_text(encoding="utf-8").splitlines() if CACHE.exists() else []:
        try:
            r = json.loads(line)
            out[r["q"]] = r["hits"]
        except ValueError:
            pass
    return out


def geocode(args) -> None:
    n, _ = mentions()
    REG.mkdir(exist_ok=True)
    have = cache()
    todo = sorted({ALIAS.get(k, k) for k, v in n.items() if v >= args.min and len(k) >= 3} - set(have))
    print(f"{len(n)} names, {sum(1 for v in n.values() if v >= args.min)} named in ≥ {args.min} entries; {len(todo)} to look up", flush=True)
    with CACHE.open("a", encoding="utf-8") as fh:
        for i, q in enumerate(todo, 1):
            try:
                hits = search(q)
            except RuntimeError as e:
                print(f"  {q}: {e}", file=sys.stderr, flush=True)
                continue
            fh.write(json.dumps({"q": q, "hits": hits}, ensure_ascii=False) + "\n")
            fh.flush()
            time.sleep(0.12)
            if i % 250 == 0:
                print(f"{i}/{len(todo)}", flush=True)
    print("done", flush=True)


def decide(q: str, hits: list[dict]) -> tuple[dict, str] | None:
    """The one place a name stands for, and the rule that says so; None if none."""
    want = norm(re.sub(r"\s*\([A-Z]{2}\)\s*$", "", q))
    canton = (re.search(r"\(([A-Z]{2})\)\s*$", q) or [None, None])[1]
    exact = [h for h in hits if norm(h["name"]) == want and h["lat"] and (not canton or h["canton"] == canton)]
    towns = [h for h in exact if h["origin"] == "gg25"]
    # «Büren» for «Büren an der Aare», «Langnau» for «Langnau im Emmental»: Bernese
    # municipalities that bear the name with an official addition
    longer = [] if canton else [h for h in hits if h["origin"] == "gg25" and h["lat"] and h["canton"] == "BE"
                                and norm(h["name"]).startswith(want + " ")]
    if len(towns) == 1 and (towns[0]["canton"] == "BE" or not longer):
        return towns[0], "Gemeinde"
    if towns or longer:
        be = [h for h in towns if h["canton"] == "BE"] + longer
        if len(be) == 1:
            return be[0], ("Gemeinde, Name mit Zusatz (Kanton Bern)" if be[0] in longer and not towns
                           else "Gemeinde, mehrdeutig (Kanton Bern bevorzugt)")
        bern = [h for h in towns if h["canton"] in BERNESE]
        if not be and len(bern) == 1:
            return bern[0], "Gemeinde, mehrdeutig (bernisches Gebiet bevorzugt)"
        return None
    places = [h for h in exact if h["origin"] == "gazetteer"]
    if len(places) == 1:
        return places[0], "Siedlung"
    be = [h for h in places if h["canton"] == "BE"]
    if len(be) == 1:
        return be[0], "Siedlung, mehrdeutig (Kanton Bern bevorzugt)"
    return None


def build(args) -> None:
    n, entries = mentions()
    have = cache()
    places: dict[str, dict] = {}      # key: place identity -> record
    of_name: dict[str, str] = {}
    unlinked = collections.Counter()
    for name, count in n.items():
        q = ALIAS.get(name, name)
        hit = decide(q, have[q]) if q in have else None
        if not hit:
            unlinked[name] += count
            continue
        h, rule = hit
        key = f"{h['origin']}:{h['id'] or h['label']}"
        p = places.setdefault(key, {"id": key, "name": h["name"], "canton": h["canton"], "lat": round(h["lat"], 5),
                                    "lon": round(h["lon"], 5), "rule": rule, "source": "swisstopo " + h["origin"],
                                    "names": {}})
        p["names"][name] = count
        if name in ALIAS and norm(ALIAS[name]) != norm(name):
            p["alias"] = True
        of_name[name] = key
    order = sorted(places.values(), key=lambda p: -sum(p["names"].values()))
    index = {p["id"]: i for i, p in enumerate(order)}
    rows = []
    for e in entries:
        named = {of_name[x.strip()] for x in e.get("orte") or [] if x.strip() in of_name}
        origin = {of_name[p["herkunft"].strip()] for p in e.get("personen") or []
                  if p.get("rolle") == "beschuldigt" and p.get("herkunft") and p["herkunft"].strip() in of_name}
        origin = {k for k in origin if places[k]["name"] not in NOT_AN_ORIGIN}
        if named or origin:
            rows.append([e["id"], sorted(index[k] for k in named), sorted(index[k] for k in origin)])
    REG.mkdir(exist_ok=True)
    out = {"places": order, "entries": rows,
           "unlinked": [[k, v] for k, v in unlinked.most_common(300)]}
    tmp = REG / "orte.part"
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(REG / "orte.json")
    total = sum(n.values())
    linked = total - sum(unlinked.values())
    print(f"{len(order)} places from {len(of_name)} names; {linked} of {total} mentions linked ({linked / total:.0%}); "
          f"{len(rows)} of {len(entries)} entries on the map")
    print("rules:", dict(collections.Counter(p["rule"] for p in order)))
    print("most frequent unlinked:", unlinked.most_common(25))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["geocode", "build"])
    ap.add_argument("--min", type=int, default=2, help="geocode: only names found in at least this many entries")
    args = ap.parse_args()
    {"geocode": geocode, "build": build}[args.step](args)


if __name__ == "__main__":
    main()

"""Registers of persons and places, with links to authority files.

    python scripts/register.py            # → register/personen.json, register/orte.json (links added)

**Places.** ``register/orte.json`` (scripts/places.py) holds the places with
their swisstopo identity. A municipality's swisstopo id is its BFS number, and
Wikidata records that number: the join to Wikidata (QID), the Historisches
Lexikon der Schweiz (HLS), GND and GeoNames is by that **identifier**, not by
name (``register/normdaten/gemeinden_wikidata.json``). Settlements below the
municipality have no such number and stay without links.

**Persons.** The entries name persons as the language model read them, in the
spelling of the source. The register groups those mentions by **name form**:
given names reduced to a common form (Hans, Hanns, Johannes → hans), the
spelling evened out (y/i, tz/z, ck/k, doubled letters). A group is a name, not
a person: two men called Hans Müller a century apart share a group, and the
register says so.

A group is compared with the persons who have an article in the HLS and died
1500–1829 (``register/normdaten/hls_personen_wikidata.json``, from Wikidata).
A mention is a candidate for an HLS person when the name form is the same, the
given names do not contradict each other (Hans Rudolf is not Hans Ludwig) and
the person was alive and at least 18 in the entry's year. The link is graded,
never certain:

* ``wahrscheinlich`` — the only HLS person of that name alive then, with all
  given names agreeing, and
  Wikidata connects that person with Bern (place of birth or death, or the
  description);
* ``möglich`` — any other candidate.

Most people in a Turmbuch have no article in any lexicon; the register is
expected to link few of them.
"""

from __future__ import annotations

import collections
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "register"

# given names: the forms the sources use → one key
GIVEN = {
    "hans": "hans", "hanns": "hans", "hannß": "hans", "hansen": "hans", "johann": "hans", "johannes": "hans", "johans": "hans",
    "joannes": "hans", "jean": "hans", "hensli": "hans", "hänsli": "hans", "hansli": "hans",
    "niclaus": "niklaus", "niklaus": "niklaus", "nicolaus": "niklaus", "niclauß": "niklaus", "claus": "niklaus", "claus": "niklaus",
    "niggli": "niklaus", "nigli": "niklaus", "nicolas": "niklaus",
    "uli": "ulrich", "ulli": "ulrich", "ulrich": "ulrich", "ullrich": "ulrich", "ueli": "ulrich", "uolrich": "ulrich", "ulrych": "ulrich",
    "peter": "peter", "petter": "peter", "pieter": "peter", "pierre": "peter",
    "jacob": "jakob", "jakob": "jakob", "jaggi": "jakob", "jacques": "jakob", "jacobus": "jakob",
    "christen": "christian", "christian": "christian", "christan": "christian", "cristen": "christian", "christoffel": "christoph",
    "stoffel": "christoph", "christoph": "christoph", "christof": "christoph",
    "bendicht": "benedikt", "benedict": "benedikt", "benedikt": "benedikt", "bendict": "benedikt", "bänz": "benedikt",
    "heinrich": "heinrich", "heini": "heinrich", "heinj": "heinrich", "henrich": "heinrich", "heinrych": "heinrich",
    "rudolf": "rudolf", "rudolff": "rudolf", "ruodolf": "rudolf", "ruedi": "rudolf", "rudi": "rudolf", "rudolph": "rudolf",
    "caspar": "kaspar", "kaspar": "kaspar", "casper": "kaspar", "conrad": "konrad", "cunrad": "konrad", "konrad": "konrad", "cuni": "konrad",
    "mathys": "matthias", "mathis": "matthias", "matthias": "matthias", "mathias": "matthias", "thys": "matthias",
    "michel": "michael", "michael": "michael", "wilhelm": "wilhelm", "wilhälm": "wilhelm", "willhelm": "wilhelm", "guillaume": "wilhelm",
    "samuel": "samuel", "sammel": "samuel", "sampel": "samuel", "daniel": "daniel", "david": "david", "abraham": "abraham",
    "anthoni": "anton", "anthony": "anton", "antoni": "anton", "anton": "anton", "thöni": "anton", "antoine": "anton",
    "anna": "anna", "anni": "anna", "anne": "anna", "barbara": "barbara", "barbli": "barbara", "babi": "barbara",
    "elsbeth": "elisabeth", "elisabeth": "elisabeth", "elsi": "elisabeth", "elßbeth": "elisabeth", "elsbet": "elisabeth",
    "madlen": "magdalena", "magdalena": "magdalena", "madlena": "magdalena", "maria": "maria", "marie": "maria",
    "margreth": "margaretha", "margret": "margaretha", "margaretha": "margaretha", "gret": "margaretha", "greti": "margaretha",
    "cathrin": "katharina", "catharina": "katharina", "katharina": "katharina", "chattrin": "katharina", "cathryn": "katharina", "trini": "katharina",
    "verena": "verena", "vreni": "verena", "freni": "verena", "frena": "verena", "ursula": "ursula", "ursel": "ursula", "ursi": "ursula",
    "franz": "franz", "frantz": "franz", "françois": "franz", "georg": "georg", "jörg": "georg", "jerg": "georg", "görg": "georg",
    "ludwig": "ludwig", "ludwyg": "ludwig", "louis": "ludwig", "vincenz": "vinzenz", "vincentz": "vinzenz", "vinzenz": "vinzenz", "zenz": "vinzenz",
    "bartlome": "bartholomaeus", "bartholome": "bartholomaeus", "bartli": "bartholomaeus", "bartholomäus": "bartholomaeus",
    "andres": "andreas", "andreas": "andreas", "andreß": "andreas", "lienhart": "leonhard", "lienhard": "leonhard", "leonhard": "leonhard",
    "bernhart": "bernhard", "bernhard": "bernhard", "gilgen": "gilg", "gilg": "gilg", "wolfgang": "wolfgang", "wolf": "wolfgang",
    "steffan": "stephan", "stephan": "stephan", "steffen": "stephan", "marti": "martin", "martin": "martin", "marty": "martin",
    "adam": "adam", "beat": "beat", "batt": "beat", "simon": "simon", "symon": "simon", "thomas": "thomas", "thoman": "thomas", "oswald": "oswald",
}
PARTICLES = {"von", "vom", "zum", "zur", "der", "de", "du", "le", "la", "im", "am", "uff", "uf", "ab", "zu", "des", "dit", "genannt", "alias", "gen"}
TITLES = {"herr", "herrn", "hr", "h", "junker", "jr", "meister", "mr", "frau", "fr", "jungfrau", "jgfr", "m", "dr", "doctor",
          "hauptmann", "landvogt", "vogt", "venner", "schultheiss", "ammann", "weibel", "grossweibel", "pfarrer", "predikant", "wittwe", "witwe", "sel"}


def plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("ß", "ss").replace("ſ", "s"))
    return "".join(c for c in s if not unicodedata.combining(c))


def even(tok: str) -> str:
    """The spelling evened out: what a scribe varied without meaning anything."""
    t = plain(tok)
    t = t.replace("y", "i").replace("j", "i").replace("tz", "z").replace("ck", "k").replace("th", "t").replace("dt", "t")
    t = t.replace("ph", "f").replace("v", "f").replace("w", "u").replace("ae", "a").replace("oe", "o").replace("ue", "u").replace("uo", "u")
    t = re.sub(r"(.)\1+", r"\1", t)
    return re.sub(r"[^a-z]", "", t)


def name_key(name: str) -> tuple[str, int]:
    """(key, number of name parts). The first given name in its common form,
    then the family name evened out; titles and particles dropped. Parts after a
    «von/de» that is followed by the last token stay (von Erlach)."""
    toks = [t for t in re.split(r"[\s,.;]+", re.sub(r"\(.*?\)", " ", name)) if t]
    toks = [t for t in toks if plain(t) not in TITLES]
    if not toks:
        return "", 0
    given = GIVEN.get(plain(toks[0]), even(toks[0]))
    rest = [even(t) for t in toks[1:] if plain(t) not in PARTICLES and not t.isdigit()]
    rest = [t for t in rest if t]
    if not rest:
        return given, 1
    # further given names are dropped when a family name follows (Hans Rudolf Tillier → hans tillier)
    family = rest[-1]
    return f"{given} {family}", 2


def given_names(name: str) -> list[str]:
    """Every given name in its common form: all name parts but the last, without
    titles and particles (Hans Rudolff Steyger → [hans, rudolf])."""
    toks = [t for t in re.split(r"[\s,.;]+", re.sub(r"\(.*?\)", " ", name)) if t and plain(t) not in TITLES]
    toks = [t for t in toks[:-1] if plain(t) not in PARTICLES and not t.isdigit()]
    return [GIVEN.get(plain(t), even(t)) for t in toks]


def same_person_name(a: list[str], b: list[str]) -> str:
    """'exact' when all given names agree, 'partial' when one side has more of
    them and the shared ones agree (Hans ~ Hans Rudolf), '' when they differ
    (Hans Rudolf against Hans Ludwig)."""
    if a == b:
        return "exact"
    n = min(len(a), len(b))
    return "partial" if n and a[:n] == b[:n] else ""


def hls_index() -> dict[str, list[dict]]:
    data = json.loads((REG / "normdaten" / "hls_personen_wikidata.json").read_text(encoding="utf-8"))["personen"]
    idx: dict[str, list[dict]] = collections.defaultdict(list)
    for p in data:
        key, n = name_key(p["name"])
        if n == 2:
            p["given"] = given_names(p["name"])
            p["bern"] = "Bern" in " ".join(p["places"]) or "Bern" in p["desc"] or "bern" in p["desc"].lower()
            idx[key].append(p)
    return idx


def alive(p: dict, year: int) -> bool:
    d = p["d"]
    b = p["b"] if p["b"] is not None else (d - 75 if d is not None else None)
    return b is not None and d is not None and b + 18 <= year <= d


def persons() -> None:
    entries = [json.loads(x) for x in (ROOT / "entries" / "entries.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    entries = [e for e in entries if e.get("regest")]
    idx = hls_index()
    groups: dict[str, dict] = {}
    for e in entries:
        for p in e.get("personen") or []:
            key, n = name_key(p["name"])
            if n < 2 or len(key) < 6:
                continue        # a single name (a first name, an office) is not a register entry
            g = groups.setdefault(key, {"key": key, "forms": collections.Counter(), "roles": collections.Counter(),
                                        "from": collections.Counter(), "years": [], "entries": [], "cand": {}})
            g["forms"][p["name"]] += 1
            g["roles"][p["rolle"]] += 1
            if p.get("herkunft"):
                g["from"][p["herkunft"]] += 1
            if e.get("year"):
                g["years"].append(e["year"])
            if e["id"] not in g["entries"]:
                g["entries"].append(e["id"])
            if e.get("year") and key in idx:
                mine = given_names(p["name"])
                cands = [(h, m) for h in idx[key] if alive(h, e["year"]) and (m := same_person_name(mine, h["given"]))]
                for h, m in cands:
                    c = g["cand"].setdefault(h["hls"], {"h": h, "n": 0, "only": 0, "entries": []})
                    c["n"] += 1
                    c["only"] += len(cands) == 1 and m == "exact"
                    if e["id"] not in c["entries"]:
                        c["entries"].append(e["id"])
    extra_path = REG / "normdaten" / "ssrq_kf_links.json"
    extra = {x["hls"]: x for x in json.loads(extra_path.read_text(encoding="utf-8"))["links"]} if extra_path.exists() else {}
    out, links = [], collections.Counter()
    for g in groups.values():
        rec = {"key": g["key"], "name": g["forms"].most_common(1)[0][0], "forms": [f for f, _ in g["forms"].most_common(6)],
               "n": len(g["entries"]), "roles": dict(g["roles"]), "from": [f for f, _ in g["from"].most_common(3)],
               "years": [min(g["years"]), max(g["years"])] if g["years"] else None, "entries": g["entries"][:200]}
        hls = []
        for c in g["cand"].values():
            h = c["h"]
            grade = "wahrscheinlich" if c["only"] == c["n"] and h["bern"] else "möglich"
            hls.append({"hls": h["hls"], "qid": h["qid"], "gnd": h["gnd"], "name": h["name"], "b": h["b"], "d": h["d"],
                        "desc": html.unescape(h["desc"]), "grade": grade, "entries": c["entries"][:50]})
            for k in ("ssrq", "kf"):      # confirmed by life dates or an identifier (register/normdaten/ssrq_kf_links.json)
                if extra.get(h["hls"], {}).get(k):
                    hls[-1][k] = extra[h["hls"]][k]
            links[grade] += 1
        if hls:
            rec["hls"] = sorted(hls, key=lambda x: (x["grade"] != "wahrscheinlich", -len(x["entries"])))
        out.append(rec)
    out.sort(key=lambda r: (r["key"].split(" ")[-1], r["key"]))
    tmp = REG / "personen.part"
    tmp.write_text(json.dumps({"persons": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(REG / "personen.json")
    multi = sum(1 for r in out if r["n"] > 1)
    print(f"persons: {len(out)} name forms ({multi} in more than one entry) from {len(entries)} entries; "
          f"HLS candidates: {dict(links)} in {sum(1 for r in out if r.get('hls'))} name forms")


def places() -> None:
    path = REG / "orte.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    towns = {g["bfs"]: g for g in json.loads((REG / "normdaten" / "gemeinden_wikidata.json").read_text(encoding="utf-8"))["gemeinden"]}
    n = 0
    for p in data["places"]:
        p.pop("links", None)
        origin, _, ident = p["id"].partition(":")
        g = towns.get(ident) if origin == "gg25" else None
        if g:
            p["links"] = {k: g[k] for k in ("qid", "hls", "gnd", "geonames") if g.get(k)}
            p["links"]["bfs"] = ident
            n += 1
    tmp = REG / "orte.part"
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    print(f"places: {n} of {len(data['places'])} linked to Wikidata/HLS by BFS number "
          f"({sum(1 for p in data['places'] if p['id'].startswith('gg25'))} are municipalities)")


if __name__ == "__main__":
    places()
    persons()

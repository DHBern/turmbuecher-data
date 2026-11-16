"""Evaluate the hand checks of the sample (scripts/pruefung.py).

    python scripts/pruefung_auswerten.py pruefung/antworten/*.json   # → pruefung/ergebnis.md

Each file is an export from the viewer's «Stichprobe prüfen». Several
reviewers' files may be given: an item checked twice counts twice, and where two
reviewers judged the same item their agreement is reported.

* Entry boundaries: precision and recall of the starts the model set, exactly
  and with one line of tolerance.
* Offences: precision and recall of the labels per entry and per category;
  share of entries whose labels were left as they were.
* Year, accused, regest, outcome, extent of the entry: shares of the verdicts;
  years split by where they came from (named, corrected, inherited).
* Persons: share of HLS links confirmed, by grade.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f} % ({a}/{b})" if b else "–"


def main() -> None:
    files = [Path(x) for x in sys.argv[1:]]
    if not files:
        sys.exit(__doc__)
    sample = json.loads((ROOT / "pruefung" / "stichprobe.json").read_text(encoding="utf-8"))
    tax = json.loads((ROOT / "taxonomy" / "delikte.json").read_text(encoding="utf-8"))
    label = {d["id"]: d["label"] for d in tax["delikte"]}
    runs = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("sample") != sample["version"]:
            print(f"  {f.name}: sample {d.get('sample')}, not {sample['version']} — skipped", file=sys.stderr)
            continue
        runs.append(d)
    out = [f"# Prüfung der Stichprobe vom {sample['version']}", "",
           f"Antworten von: {', '.join(r.get('reviewer') or 'ohne Kürzel' for r in runs)}.", ""]

    # --- boundaries
    tp = fp = fn = tp1 = fp1 = fn1 = pages = 0
    for r in runs:
        for key, a in r["answers"]["grenzen"].items():
            model, truth = set(a["model"]), set(a["starts"])
            pages += 1
            tp += len(model & truth); fp += len(model - truth); fn += len(truth - model)
            near = lambda x, ys: any(abs(x - y) <= 1 for y in ys)  # noqa: E731
            tp1 += sum(1 for m in model if near(m, truth)); fp1 += sum(1 for m in model if not near(m, truth))
            fn1 += sum(1 for x in truth if not near(x, model))
    out += ["## Eintragsgrenzen", "", f"{pages} Seiten geprüft.", "",
            "| | genau | ±1 Zeile |", "|---|---|---|",
            f"| Präzision (gesetzte Beginne, die stimmen) | {pct(tp, tp + fp)} | {pct(tp1, tp1 + fp1)} |",
            f"| Ausbeute (tatsächliche Beginne, die gesetzt sind) | {pct(tp, tp + fn)} | {pct(tp1 - 0, tp1 + fn1)} |", ""]

    # --- offences and the rest of the description
    per = collections.defaultdict(lambda: [0, 0, 0])   # category: tp, fp, fn
    same = n = 0
    verdict = collections.defaultdict(collections.Counter)
    years = collections.defaultdict(collections.Counter)
    for r in runs:
        for eid, a in r["answers"]["delikte"].items():
            n += 1
            m, t = set(a["model"]), set(a["delikte"])
            same += m == t
            for c in m & t: per[c][0] += 1
            for c in m - t: per[c][1] += 1
            for c in t - m: per[c][2] += 1
            for k in ("san", "person", "regest", "bound"):
                if a.get(k):
                    verdict[k][a[k]] += 1
            years[(a.get("year_source") or "").split(" (")[0]][a.get("year") or ""] += 1
    TP, FP, FN = (sum(v[i] for v in per.values()) for i in range(3))
    out += ["## Delikte und Regesten", "", f"{n} Einträge geprüft; bei {pct(same, n)} blieben die Delikte unverändert.", "",
            f"Delikte insgesamt: Präzision {pct(TP, TP + FP)}, Ausbeute {pct(TP, TP + FN)}.", "",
            "| Kategorie | richtig vergeben | zu Unrecht | gefehlt |", "|---|---|---|---|"]
    for c, (a, b, cc) in sorted(per.items(), key=lambda kv: -sum(kv[1])):
        out.append(f"| {label.get(c, c)} | {a} | {b} | {cc} |")
    names = {"san": "Ausgang", "person": "Beschuldigte im Titel", "regest": "Regest", "bound": "Umfang des Eintrags"}
    words = {"ok": "stimmt", "no": "falsch", "?": "nicht zu entscheiden", "part": "teilweise", "short": "zu kurz", "long": "zu lang"}
    out += ["", "| Angabe | Urteile |", "|---|---|"]
    for k, cnt in verdict.items():
        tot = sum(cnt.values())
        out.append(f"| {names[k]} | " + ", ".join(f"{words.get(v, v)} {pct(c, tot)}" for v, c in cnt.most_common()) + " |")
    out += ["", "| Jahr, Herkunft | Urteile |", "|---|---|"]
    for src, cnt in years.items():
        tot = sum(cnt.values())
        out.append(f"| {src or '–'} | " + ", ".join(f"{words.get(v, v or '–')} {pct(c, tot)}" for v, c in cnt.most_common()) + " |")

    # --- persons
    pg = collections.defaultdict(collections.Counter)
    for r in runs:
        for key, a in r["answers"]["personen"].items():
            pg[a["grade"]][a["same"]] += 1
    out += ["", "## Personen im HLS", "", "| Stufe | Urteile |", "|---|---|"]
    for g, cnt in pg.items():
        tot = sum(cnt.values())
        out.append(f"| {g} | " + ", ".join(f"{ {'ok': 'dieselbe Person', 'no': 'eine andere', '?': 'nicht zu entscheiden'}.get(v, v)} {pct(c, tot)}" for v, c in cnt.most_common()) + " |")

    # --- agreement where an item was judged twice
    if len(runs) > 1:
        agree = tot = 0
        for task, key in (("delikte", "delikte"), ("personen", "same"), ("grenzen", "starts")):
            seen = collections.defaultdict(list)
            for r in runs:
                for i, a in r["answers"][task].items():
                    seen[i].append(sorted(a[key]) if isinstance(a[key], list) else a[key])
            for v in seen.values():
                if len(v) > 1:
                    tot += 1
                    agree += all(x == v[0] for x in v)
        out += ["", "## Übereinstimmung", "", f"Doppelt geprüfte Stücke: {pct(agree, tot)} gleich beurteilt."]

    notes = [(t, i, a["note"]) for r in runs for t in ("grenzen", "delikte", "personen") for i, a in r["answers"][t].items() if a.get("note")]
    if notes:
        out += ["", "## Bemerkungen", ""] + [f"- {t} {i}: {nt}" for t, i, nt in notes]
    (ROOT / "pruefung" / "ergebnis.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()

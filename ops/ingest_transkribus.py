"""Ingest of Transkribus collection 187323 (StABE_Turmbücher_DH_flow): metadata and PAGE XML.

Runs on tei, inside the agentic_historian checkout (its Transkribus session):

    cd ~/agentic_historian
    PYTHONPATH=./agentic_historian:$PWD .venv/bin/python3 <this file> OUT [--docs 1334763,1334819]

Writes ``OUT/manifest.jsonl`` (one row per page) and ``OUT/pagexml/<key>.xml``
(the page's latest transcript). Reads only; posts nothing to Transkribus.
Resumable: a PAGE XML already on disk is not fetched again; the manifest is
rebuilt for the documents of this run and kept for the others.

A row: ``key`` (``B_IX_422_p0001``), ``doc`` (``B IX 422``), ``docId``,
``pageNr``, ``width``, ``height`` (as Transkribus states them), ``tk`` (the
image's identifier on files.transkribus.eu), ``img`` (file name), ``status``,
``lines``, ``transcribed_lines``, ``versions`` (per transcript version: status,
toolName, timestamp, transcribed_lines). **No user names**: Transkribus keeps
the account of every version, and it is never read into a row.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from agentic_historian.ruemlang import transkribus_pages as tp

COL = 187323


def slug(title: str) -> str:
    """'B IX 428 (1564-1566)' -> 'B_IX_428'; 'B IX 498 (neu)' -> 'B_IX_498'."""
    t = re.sub(r"\s*\(.*?\)\s*", "", title).strip()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--docs", default="", help="comma-separated docIds; default: the whole collection")
    args = ap.parse_args()
    (args.out / "pagexml").mkdir(parents=True, exist_ok=True)
    ts = tp.TkSession().authenticate()
    docs = ts.get_json(f"{tp.API}/collections/{COL}/list", "cannot list the collection")
    want = {int(x) for x in args.docs.split(",") if x.strip()}
    docs = [d for d in docs if not want or d["docId"] in want]
    slugs = [slug(d["title"]) for d in docs]
    if len(set(slugs)) != len(slugs):
        sys.exit("two documents share a key prefix")

    manifest = args.out / "manifest.jsonl"
    kept = []
    if manifest.exists():
        ids = {d["docId"] for d in docs}
        kept = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
        kept = [r for r in kept if r["docId"] not in ids]
    rows, fetched = [], 0
    for d in docs:
        c = ts.get_json(f"{tp.API}/collections/{COL}/{d['docId']}/fulldoc", f"cannot read {d['docId']}")
        title = str(c["md"]["title"]).strip()
        for p in c["pageList"]["pages"]:
            vs = (p.get("tsList") or {}).get("transcripts") or []
            latest = vs[0] if vs else {}
            key = f"{slug(title)}_p{int(p['pageNr']):04d}"
            rows.append({
                "key": key, "doc": title, "docId": d["docId"], "pageNr": int(p["pageNr"]),
                "width": p.get("width"), "height": p.get("height"),
                "tk": p.get("key"), "img": p.get("imgFileName"),
                "status": latest.get("status"),
                "lines": int(latest.get("nrOfLines") or 0),
                "transcribed_lines": int(latest.get("nrOfTranscribedLines") or 0),
                "versions": [{"status": v.get("status"), "toolName": v.get("toolName") or "",
                              "timestamp": v.get("timestamp"),
                              "transcribed_lines": int(v.get("nrOfTranscribedLines") or 0)} for v in vs],
            })
            dest = args.out / "pagexml" / f"{key}.xml"
            if latest.get("url") and not (dest.exists() and dest.stat().st_size):
                r = ts.get(latest["url"])
                if r.status_code != 200:
                    print(f"  {key}: PAGE XML {r.status_code}", file=sys.stderr)
                    continue
                tmp = dest.with_suffix(".part")
                tmp.write_bytes(r.content)
                tmp.replace(dest)
                fetched += 1
        print(f"{title}: {len(c['pageList']['pages'])} pages", flush=True)
    out = kept + rows
    tmp = manifest.with_suffix(".part")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    tmp.replace(manifest)
    print(f"manifest: {len(out)} pages ({len(rows)} from this run); PAGE XML fetched: {fetched}")


if __name__ == "__main__":
    main()

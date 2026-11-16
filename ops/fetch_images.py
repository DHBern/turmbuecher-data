"""Page images for the readers, from the Transkribus IIIF server.

    python3 fetch_images.py OUT [--volumes "B IX 422,B IX 467"] [--side 3000]

Reads ``OUT/manifest.jsonl`` (ops/ingest_transkribus.py) and writes
``OUT/pages/<key>.jpg``: the page as the IIIF server delivers it, i.e. already
turned upright (the uploaded files carry an EXIF rotation; the PAGE XML
coordinates refer to the upright image), longest side at most ``--side`` px.
Resumable; needs no login (the image keys are public identifiers).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

IIIF = "https://files.transkribus.eu/iiif/2/"


def fetch(row: dict, out: Path, side: int) -> str:
    dest = out / f"{row['key']}.jpg"
    if dest.exists() and dest.stat().st_size > 10_000:
        return "kept"
    url = f"{IIIF}{row['tk']}/full/!{side},{side}/0/default.jpg"
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(url, timeout=120).read()
            if len(data) < 10_000 or data[:2] != b"\xff\xd8":
                raise ValueError(f"not a JPEG ({len(data)} bytes)")
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return "fetched"
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:120]
            time.sleep(3 * (attempt + 1))
    print(f"  {row['key']}: {err}", file=sys.stderr, flush=True)
    return "failed"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--volumes", default="", help="comma-separated document titles (prefix match); default: all")
    ap.add_argument("--side", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    rows = [json.loads(x) for x in (args.out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    want = [v.strip() for v in args.volumes.split(",") if v.strip()]
    rows = [r for r in rows if r.get("tk") and (not want or any(r["doc"].startswith(v) for v in want))]
    (args.out / "pages").mkdir(exist_ok=True)
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(args.workers) as ex:
        for i, res in enumerate(ex.map(lambda r: fetch(r, args.out / "pages", args.side), rows), 1):
            counts[res] = counts.get(res, 0) + 1
            if i % 100 == 0:
                print(f"{i}/{len(rows)} {counts}", flush=True)
    print(f"done: {len(rows)} pages {counts}", flush=True)


if __name__ == "__main__":
    main()

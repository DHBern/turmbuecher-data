"""Page images for the readers, from the Transkribus IIIF server.

    python3 fetch_images.py OUT [--volumes "B IX 422,B IX 467"] [--side 3000]

Reads ``OUT/manifest.jsonl`` (ops/ingest_transkribus.py) and writes
``OUT/pages/<key>.jpg``: the page as the IIIF server delivers it, i.e. already
turned upright (the uploaded files carry an EXIF rotation; the PAGE XML
coordinates refer to the upright image), longest side at most ``--side`` px.
Where the IIIF server refuses the size (403, whole volumes on 16.11.2026), the
original file is fetched instead and turned upright and scaled here, needing
Pillow. Resumable; needs no login (the image keys are public identifiers).
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


def from_original(row: dict, dest: Path, side: int) -> None:
    """The original file (Transkribus ``Get?fileType=orig``), turned upright by its
    EXIF orientation and scaled to at most ``side``: the same image the IIIF
    server would deliver. Used where the IIIF server refuses the size (403)."""
    import io
    from PIL import Image, ImageOps
    data = urllib.request.urlopen(f"https://files.transkribus.eu/Get?id={row['tk']}&fileType=orig", timeout=300).read()
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if row.get("width") and row.get("height") and im.size != (int(row["width"]), int(row["height"])):
        raise ValueError(f"upright original is {im.size}, Transkribus says {row['width']}x{row['height']}")
    im.thumbnail((side, side))
    tmp = dest.with_suffix(".part")
    im.convert("RGB").save(tmp, "JPEG", quality=90)
    tmp.replace(dest)


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
            if "HTTP Error 403" in str(e) or getattr(e, "code", None) == 403:
                try:
                    from_original(row, dest, side)
                    return "original"
                except Exception as e2:  # noqa: BLE001
                    err = "original: " + repr(e2)[:120]
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

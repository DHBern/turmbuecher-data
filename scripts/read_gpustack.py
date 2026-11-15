"""A reading of the page images by an open vision-language model on GPUStack.

    python scripts/read_gpustack.py [--volumes "B IX 467"] [--model qwen3.8-27b] [--limit 3]

One call per page: the page image (from the Transkribus IIIF server, longest
side ``SIDE`` px) and ``prompts/turmbuch_page_v1.md``. Appends to
``readings/<model>.jsonl`` (``key``, ``text``, ``truncated`` when the model hit
its token ceiling); a page already read is skipped, so an interrupted run is
resumed by starting it again.

Tried on 15.11.2026 with qwen3.8-27b without fine-tuning and stopped after 113
pages: on 92 of them the model ran into its token ceiling repeating invented
phrases. It does not read these hands; its output is not published. The script
stays for a model that does.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IIIF = "https://files.transkribus.eu/iiif/2/"
SIDE = 2000
PROMPT = (ROOT / "prompts" / "turmbuch_page_v1.md").read_text(encoding="utf-8")


def image_b64(tk: str) -> str:
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(f"{IIIF}{tk}/full/!{SIDE},{SIDE}/0/default.jpg", timeout=120).read()
            if data[:2] == b"\xff\xd8":
                return base64.b64encode(data).decode()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("image not available")


def read(model: str, tk: str) -> tuple[str, bool]:
    base, key = os.environ["GPUSTACK_BASE_URL"].rstrip("/"), os.environ["GPUSTACK_API_KEY"]
    body = json.dumps({
        "model": model, "temperature": 0, "max_tokens": 4096,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64(tk)}},
            {"type": "text", "text": PROMPT}]}],
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    err = ""
    for attempt in range(4):
        req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.loads(r.read())
            c = d["choices"][0]
            return (c["message"].get("content") or "").strip(), c.get("finish_reason") == "length"
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:120]
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(err)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volumes", default="")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    with (ROOT / "readings" / "pages.tsv").open(encoding="utf-8") as fh:
        pages = list(csv.DictReader(fh, delimiter="\t"))
    want = [v.strip() for v in args.volumes.split(",") if v.strip()]
    out = ROOT / "readings" / f"{args.model}.jsonl"
    done = {json.loads(x)["key"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()} if out.exists() else set()
    todo = [p for p in pages if p["tk"] and p["key"] not in done and (not want or p["volume"] in want)]
    if args.limit:
        todo = todo[: args.limit]
    lock, n = threading.Lock(), [0, 0]
    digest = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]

    def one(p: dict) -> None:
        try:
            text, cut = read(args.model, p["tk"])
            rec = {"key": p["key"], "text": text, "prompt": digest}
            if cut:
                rec["truncated"] = True
            with lock, out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            n[1] += 1
            print(f"  {p['key']}: {repr(e)[:120]}", file=sys.stderr, flush=True)
        n[0] += 1
        if n[0] % 25 == 0:
            print(f"{n[0]}/{len(todo)} ({n[1]} failed)", flush=True)

    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(one, todo))
    print(f"done: {len(todo)} pages asked, {n[1]} failed", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read every Transkribus line of the Turmbücher with a TrOCR model (UBELIX, inside a container).

    python read_lines.py --root DIR --model HF_REPO --name NAME --out FILE.jsonl [--shard i --shards n]

Input (ROOT = turmbuecher-images on the research share): manifest.jsonl,
pagexml/<key>.xml (the Transkribus lines), pages/<key>.jpg (the page as the
IIIF server delivers it: upright, scaled to at most 3000 px, so the line
polygons are scaled by image width ÷ the PAGE XML's imageWidth).

Output: one JSON line per page, {"key", "model", "lines": [{"id", "text", "conf"}]},
the lines in the PAGE XML's order. Pages already in FILE are skipped (resumable);
pages are split across shards by a stable hash of the key.
Adapted from the Felix V reader (datasets/felix-v/read_lines.py).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def pts(s: str) -> list[tuple[float, float]]:
    out = []
    for tok in (s or "").split():
        if "," in tok:
            x, y = tok.split(",", 1)
            out.append((float(x), float(y)))
    return out


def page_lines(xml_path: Path) -> tuple[int, list[dict]]:
    root = ET.parse(xml_path).getroot()
    width, lines = 0, []
    for el in root.iter():
        t = local(el.tag)
        if t == "Page":
            width = int(el.get("imageWidth") or 0)
        elif t == "TextLine":
            c = next((x for x in el if local(x.tag) == "Coords"), None)
            poly = pts(c.get("points")) if c is not None else []
            if len(poly) >= 3:
                lines.append({"id": el.get("id"), "poly": poly})
    return width, lines


class TrocrReader:
    def __init__(self, model: str, device: str, batch: int):
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        self.torch = torch
        self.proc = TrOCRProcessor.from_pretrained(model)
        self.model = VisionEncoderDecoderModel.from_pretrained(model).to(device).eval()
        if device.startswith("cuda"):
            self.model = self.model.half()
        self.device, self.batch = device, batch

    def read(self, im: Image.Image, lines: list[dict], scale: float) -> list[dict]:
        out = []
        for k in range(0, len(lines), self.batch):
            chunk = lines[k:k + self.batch]
            crops = []
            for l in chunk:
                xs, ys = [p[0] * scale for p in l["poly"]], [p[1] * scale for p in l["poly"]]
                box = (max(0, int(min(xs))), max(0, int(min(ys))), min(im.width, int(max(xs)) + 1), min(im.height, int(max(ys)) + 1))
                if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                    box = (0, 0, 4, 4)
                crops.append(im.crop(box).convert("RGB"))
            pv = self.proc(images=crops, return_tensors="pt").pixel_values.to(self.device)
            if self.device.startswith("cuda"):
                pv = pv.half()
            with self.torch.no_grad():
                gen = self.model.generate(pv, max_new_tokens=160, num_beams=1, output_scores=True,
                                          return_dict_in_generate=True)
            texts = self.proc.batch_decode(gen.sequences, skip_special_tokens=True)
            scores = self.model.compute_transition_scores(gen.sequences, gen.scores, normalize_logits=True)
            for l, t, sc in zip(chunk, texts, scores):
                valid = sc[sc > -1e4]
                conf = float(valid.exp().mean()) if len(valid) else None
                out.append({"id": l["id"], "text": t.strip(), "conf": round(conf, 3) if conf is not None else None})
        return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()

    keys = [json.loads(x)["key"] for x in (args.root / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    keys = [k for k in keys if zlib.crc32(k.encode()) % args.shards == args.shard]
    done = set()
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["key"])
            except (ValueError, KeyError):
                pass
    todo = [k for k in keys if k not in done and (args.root / "pages" / f"{k}.jpg").exists()
            and (args.root / "pagexml" / f"{k}.xml").exists()]
    missing = sum(1 for k in keys if k not in done and not (args.root / "pages" / f"{k}.jpg").exists())
    todo = todo[: args.limit]
    print(f"{args.name}: {len(todo)} pages to read, {len(done)} done, {missing} without image (shard {args.shard}/{args.shards})", flush=True)
    if not todo:
        return 0
    reader = TrocrReader(args.model, args.device, args.batch)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with args.out.open("a", encoding="utf-8") as fh:
        for i, k in enumerate(todo, 1):
            width, lines = page_lines(args.root / "pagexml" / f"{k}.xml")
            if not lines:
                fh.write(json.dumps({"key": k, "model": args.name, "lines": []}) + "\n")
                continue
            im = Image.open(args.root / "pages" / f"{k}.jpg")
            im.load()
            try:
                res = reader.read(im, lines, im.width / width if width else 1.0)
            except Exception as e:  # noqa: BLE001 — one bad page must not end the shard
                print(f"{k}: ERROR {type(e).__name__}: {e}", flush=True)
                continue
            fh.write(json.dumps({"key": k, "model": args.name, "lines": res}, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 50 == 0 or i <= 2:
                print(f"{i}/{len(todo)} {k}: {len(res)} lines, {(time.time() - t0) / i:.2f} s/page", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

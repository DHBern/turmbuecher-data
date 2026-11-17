"""One chat call to the open language model on the University of Bern's GPUStack.

``GPUSTACK_BASE_URL`` and ``GPUSTACK_API_KEY`` come from the environment (never
from a file in this repository). The model is a reasoning model; thinking is
switched off (``enable_thinking: false``), since extraction is not a reasoning
task and thinking is spent against the token ceiling.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("TB_LLM_MODEL", "qwen3.8-27b")


def chat(system: str, user: str, max_tokens: int = 1500) -> str:
    base, key = os.environ["GPUSTACK_BASE_URL"].rstrip("/"), os.environ["GPUSTACK_API_KEY"]
    body = json.dumps({
        "model": MODEL, "temperature": 0, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    err = ""
    for attempt in range(5):
        req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            return d["choices"][0]["message"].get("content") or ""
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:120]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"model call failed: {err}")


def parse_json(text: str):
    """The first JSON object or array in a model answer (code fences tolerated)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in the answer")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except json.JSONDecodeError:
        return json.JSONDecoder().raw_decode(_loose_strings(text[start:]))[0]


_STR = r'"(?:[^"\\]|\\.)*"'
_LOOSE = re.compile(rf'^(\s*"[^"]+":\s*)({_STR}(?:\s*,\s*{_STR})+)(\s*,?\s*)$', re.M)


def _loose_strings(text: str) -> str:
    """A key followed by several strings without brackets (``"k": "a", "b",``),
    which the model writes now and then for a quoted field: joined into one string."""
    def join(m: re.Match) -> str:
        parts = [json.loads(s) for s in re.findall(_STR, m.group(2))]
        return m.group(1) + json.dumps("; ".join(parts), ensure_ascii=False) + m.group(3)
    return _LOOSE.sub(join, text)

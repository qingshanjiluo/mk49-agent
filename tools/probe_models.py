"""Probe configured LLM channels for usable, higher-capability models.

litellm config stores `model: "openai/xxx"` (provider-prefixed); upstream
OpenAI-compatible endpoints want the bare name -> strip exactly one prefix.
"""
import os
import re
import time

import requests

CFG = r"G:\皮皮\编程项目\05_应用与平台\litellm\config.yaml"
ENVF = r"G:\皮皮\编程项目\05_应用与平台\litellm\.env"

env = {}
for line in open(ENVF, encoding="utf-8", errors="replace"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'").strip('"')

cfg = open(CFG, encoding="utf-8", errors="replace").read()
pairs = re.findall(
    r'model_name:\s*"([^"]+)"\s*\n\s*litellm_params:\s*\n\s*model:\s*"([^"]+)"'
    r"\s*\n\s*api_base:\s*(\S+)\s*\n\s*api_key:\s*os.environ/(\S+)",
    cfg,
)
print("parsed entries:", len(pairs))


def bare(model):
    """Strip exactly one leading openai/ provider prefix."""
    return model[7:] if model.startswith("openai/") else model


model_bases = {}
for name, litellm_model, base, keyn in pairs:
    model_bases.setdefault(name, []).append((base, env.get(keyn), bare(litellm_model)))

SMART = ["deepseek-v4-pro", "gpt-6-sol", "gpt-6-astra", "kimi-k3", "minimax-m3",
         "glm-5.3", "gpt-5.6-sol", "agnes-3.0-flash", "glm-5.3-flashx",
         "deepseek-v4.1-flash", "qwen/qwen3.8-27b", "agnes-2.5-flash"]

s = requests.Session()
s.trust_env = False
alive = []
for name in SMART:
    for base, key, send_model in model_bases.get(name, []):
        if not key:
            continue
        t0 = time.time()
        try:
            r = s.post(
                base.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                json={"model": send_model,
                      "messages": [{"role": "user", "content": "回复OK两个字"}],
                      "max_tokens": 16, "temperature": 0},
                timeout=45,
            )
            data = r.json()
        except Exception as e:
            print("%-16s %-32s EXC %s" % (name, base, str(e)[:80]))
            continue
        if "error" in data or r.status_code >= 400:
            msg = str(data.get("error", r.status_code))[:100]
            print("%-16s %-32s ERR %s" % (name, base, msg))
            continue
        ms = int((time.time() - t0) * 1000)
        print("%-16s %-32s OK %5dms send_model=%s" % (name, base, ms, send_model))
        alive.append((name, base, key, send_model, ms))

print("\n=== alive: %d ===" % len(alive))

# ---- quality eval on alive smart models ----
QUALITY_PROMPT = (
    "论坛帖子：新手提问「驱逐和巡洋前期练哪条线，资源紧张」。"
    "作为老玩家写一条200字左右的回帖，要有具体取舍理由和1个实用小建议，"
    "口语自然像真人，不要分点罗列成说明书。"
)
seen = set()
for name, base, key, send_model, _ms in alive:
    if name in seen:
        continue
    seen.add(name)
    t0 = time.time()
    try:
        r = s.post(
            base.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            json={"model": send_model,
                  "messages": [{"role": "system", "content": "只输出正文。"},
                               {"role": "user", "content": QUALITY_PROMPT}],
                  "max_tokens": 320, "temperature": 0.9},
            timeout=90,
        )
        c = r.json()["choices"][0]["message"]
        text = c.get("content") or c.get("reasoning_content") or ""
        print("\n--- %s (%dms) ---\n%s" % (name, int((time.time() - t0) * 1000), text[:400]))
    except Exception as e:
        print("\n--- %s QUALITY EXC %s" % (name, str(e)[:100]))

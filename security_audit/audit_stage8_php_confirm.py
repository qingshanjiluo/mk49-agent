# -*- coding: utf-8 -*-
"""阶段8：确认 .php 上传落点真实存在 + 清理测试上传物（只删自己传的）。"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from mbbs.client import MBBSClient, MBBSAPIError  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ORIGIN = "https://mk48by049.mbbs.cc"
OUT = Path(__file__).resolve().parent / "out"

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "files": []}
c = MBBSClient(ORIGIN, CFG["username"], CFG["password"])
if not c.login(max_attempts=8):
    sys.exit(2)

# 重新上传一个干净 .php 探针拿正确 path，确认落点真实 + 直接清理
probe = ("probe2.php", b"plain text probe, no code")
fname, content = probe
try:
    resp = c.upload_resource(content, fname, "text/plain")
    fp = (resp or {}).get("filePath") or ""
    url = c.abs_resource_url(fp)
    report["files"].append({"file": fname, "filePath": fp, "url": url})
    print("[upload] %s -> %s" % (fname, fp))
    # 确认落点真实（正确 URL 拉取）
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        report["files"][-1]["served_status"] = r.status_code
        report["files"][-1]["served_content"] = r.text[:150]
        print("  served[%s]: %r" % (r.status_code, r.text[:120]))
    except Exception as e:
        report["files"][-1]["fetch_error"] = str(e)[:150]
    # 清理测试物
    try:
        c.delete_resource(fp)
        report["files"][-1]["cleaned"] = True
        print("  cleaned:", fp)
    except Exception as e:
        report["files"][-1]["clean_error"] = str(e)[:150]
        print("  clean error:", str(e)[:120])
except Exception as e:
    print("[upload] error:", e)

(OUT / "audit_stage8_php_confirm.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage8_php_confirm.json")
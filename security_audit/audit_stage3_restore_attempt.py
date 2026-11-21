# -*- coding: utf-8 -*-
"""阶段3：修复尝试 — 用 zzhx 会话对被黑站执行 setting/set 写回原值。
预期：认证用户无管理权限 → 403/无权（证明权限模型完好）。
意外收获路径：若写入成功 = 存在越权漏洞 = 直接完成修复。
写回的键与值均为恢复原状操作（site_name/site_introduction/清空注入 HTML）。
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbbs.client import MBBSClient, MBBSAPIError  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ORIGIN = "https://mk48by049.mbbs.cc"
OUT = Path(__file__).resolve().parent / "out"

RESTORE = {
    "site_name": "龙之归宿",
    "site_introduction": "mk49 | 龙之归宿",
    "site_custom_append_body_html": "",
}

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "attempts": []}

c = MBBSClient(ORIGIN, CFG["username"], CFG["password"])
if not c.login(max_attempts=8):
    print("[FATAL] login failed")
    sys.exit(2)
print("[login] ok id=%s group=%s" % (c.user_id, (c.user.get("group") or {}).get("name")))

for key, value in RESTORE.items():
    try:
        resp = c.post("setting/set", {"key": key, "value": value})
        report["attempts"].append({"key": key, "result": "OK", "resp": resp})
        print("[SET %s] 成功: %s" % (key, json.dumps(resp, ensure_ascii=False)[:300]))
    except MBBSAPIError as e:
        report["attempts"].append({"key": key, "result": "DENIED",
                                   "status": e.status, "message": str(e)[:300],
                                   "payload": e.payload})
        print("[SET %s] 拒绝: status=%s msg=%s" % (key, e.status, str(e)[:200]))
    except Exception as e:
        report["attempts"].append({"key": key, "result": "ERROR", "error": str(e)[:300]})
        print("[SET %s] 异常: %s" % (key, e))
    time.sleep(1)

# 修复后复查（只读 getAll）
try:
    cur = c.get("setting/getAll").get("data") or {}
    check = {k: cur.get(k) for k in ("site_name", "site_introduction",
                                     "site_custom_append_body_html",
                                     "site_keywords", "ui_power_by_text")}
    report["after_check"] = check
    print("[复查]", json.dumps(check, ensure_ascii=False, indent=1)[:1500])
except Exception as e:
    report["after_check"] = {"error": str(e)}

(OUT / "audit_stage3_restore_attempt.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage3_restore_attempt.json")

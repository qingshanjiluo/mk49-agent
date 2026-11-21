# -*- coding: utf-8 -*-
"""阶段4：管理面鉴权边界探针 + zzhx 收件箱取证。
全部为只读/被拒即止的探测：
1. GET manage/listForums（平台租户列表）
2. POST manage/getForumAdminToken {db_name}(尝试自己站)
3. POST manage/trialLevel2（试用升级，无参）
4. GET message/listMessage（zzhx 站内信取证）
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

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "probes": []}

c = MBBSClient(ORIGIN, CFG["username"], CFG["password"])
if not c.login(max_attempts=8):
    sys.exit(2)


def probe(name, method, path, body=None):
    try:
        if method == "GET":
            r = c.get(path, params=body)
        else:
            r = c.post(path, body)
        entry = {"name": name, "result": "OK", "resp": r}
        print("[%s] OK: %s" % (name, json.dumps(r, ensure_ascii=False)[:800]))
    except MBBSAPIError as e:
        entry = {"name": name, "result": "DENIED", "status": e.status,
                 "message": str(e)[:400]}
        print("[%s] DENIED: %s" % (name, str(e)[:300]))
    except Exception as e:
        entry = {"name": name, "result": "ERROR", "error": str(e)[:400]}
        print("[%s] ERROR: %s" % (name, e))
    report["probes"].append(entry)
    time.sleep(0.8)


probe("manage/listForums", "GET", "manage/listForums",
      {"page_limit": 20, "page_offset": 0})
probe("manage/getForumAdminToken(mk48by049)", "POST",
      "manage/getForumAdminToken", {"db_name": "mk48by049"})
probe("manage/trialLevel2", "POST", "manage/trialLevel2")

# 收件箱取证
try:
    msgs, total = c.list_messages(page_limit=50)
    report["inbox"] = {"total": total, "messages": [
        {"id": m.get("id"), "title": (m.get("title") or "")[:80],
         "from": ((m.get("from_user") or {}).get("name")),
         "created_at": m.get("created_at")} for m in msgs]}
    print("[inbox] total=%s" % total)
    for m in report["inbox"]["messages"][:15]:
        print("  -", m)
except Exception as e:
    report["inbox"] = {"error": str(e)}
    print("[inbox] error:", e)

(OUT / "audit_stage4_admin_probe.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage4_admin_probe.json")

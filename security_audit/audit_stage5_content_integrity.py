# -*- coding: utf-8 -*-
"""阶段5：被黑站内容完整性盘点（只读）。
1. 全分类帖子总数对比（数据是否被清空）
2. 站长/管理员账号定位（id 1~10 探测 + group 字段）
3. moderation-records 管理操作留痕
4. 最新帖子时间线（最后正常活动时间）
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

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S")}

c = MBBSClient(ORIGIN, CFG["username"], CFG["password"])
if not c.login(max_attempts=8):
    sys.exit(2)

# 1. 分类与帖子总数
cats = c.categories()
cat_report = []
for cat in cats:
    cid = cat.get("id")
    try:
        _, total = c.list_threads(category_id=cid, page_limit=1, sort="-created_at")
        latest, _ = c.list_threads(category_id=cid, page_limit=3, sort="-created_at")
        cat_report.append({
            "id": cid, "name": cat.get("name"), "total": total,
            "latest": [{"id": t.get("id"), "title": (t.get("title") or "")[:40],
                        "created_at": t.get("created_at")} for t in latest],
        })
    except Exception as e:
        cat_report.append({"id": cid, "name": cat.get("name"), "error": str(e)[:120]})
report["categories"] = cat_report
print("[categories]")
for x in cat_report:
    print(" ", x.get("name"), "total=", x.get("total"),
          "latest=", (x.get("latest") or [{}])[0].get("created_at"),
          ((x.get("latest") or [{}])[0].get("title") or "") if x.get("latest") else "")
    time.sleep(0.5)

# 2. 站长定位：id 1~12
admins = []
for uid in range(1, 13):
    try:
        u = c.get_user(uid)
        if u:
            admins.append({"id": u.get("id"), "name": u.get("name"),
                           "group": (u.get("group") or {}).get("name"),
                           "created_at": u.get("created_at")})
    except Exception:
        pass
    time.sleep(0.3)
report["early_users"] = admins
print("[early_users]", json.dumps(admins, ensure_ascii=False))

# 3. moderation-records 留痕
try:
    payload = c.get("moderation-records/list",
                    params={"page_limit": 30, "page_offset": 0})
    report["moderation_records"] = {"count": len(payload.get("data") or []),
                                    "list": (payload.get("data") or [])[:30]}
    print("[moderation] count=", len(payload.get("data") or []))
except Exception as e:
    report["moderation_records"] = {"error": str(e)[:200]}
    print("[moderation] error:", e)

# 4. 全站最新活动（不带分类）
try:
    latest, total = c.list_threads(page_limit=10, sort="-created_at")
    report["site_latest"] = {"total": total, "list": [
        {"id": t.get("id"), "title": (t.get("title") or "")[:50],
         "created_at": t.get("created_at")} for t in latest]}
    print("[site] total_threads=", total)
    for t in report["site_latest"]["list"][:10]:
        print("  -", t)
except Exception as e:
    report["site_latest"] = {"error": str(e)[:200]}

(OUT / "audit_stage5_content_integrity.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage5_content_integrity.json")

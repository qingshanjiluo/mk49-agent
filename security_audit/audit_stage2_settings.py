# -*- coding: utf-8 -*-
"""阶段2：对比平台被黑站(mk48by049.mbbs.cc)与自有站(forum.mk49.top)的站点设置。
只读：GET setting/getAll；登录尝试用现有凭据；不做任何写操作。
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from mbbs.client import MBBSClient  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = Path(__file__).resolve().parent / "out"

TARGETS = {
    "platform_hacked": "https://mk48by049.mbbs.cc",
    "selfhost_clean": "https://forum.mk49.top",
}

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S")}


def anon_settings(origin):
    """匿名拉取 setting/getAll（公开可读部分）。"""
    try:
        r = requests.get(origin + "/bbs/setting/getAll", timeout=15,
                         headers={"User-Agent": "Mozilla/5.0", "Origin": origin,
                                  "Referer": origin + "/"})
        try:
            j = r.json()
        except ValueError:
            return {"status": r.status_code, "body": r.text[:300]}
        if isinstance(j, dict) and j.get("success") is False:
            return {"status": r.status_code, "message": j.get("message")}
        return {"status": r.status_code, "data": (j or {}).get("data")}
    except Exception as e:
        return {"error": str(e)}


for name, origin in TARGETS.items():
    report[name] = {"anon_setting_getAll": anon_settings(origin)}
    print("=" * 20, name, "=" * 20)
    print(json.dumps(report[name], ensure_ascii=False, indent=1)[:4000])

# zzhx 登录平台被黑站试探（同一凭据是否在平台站有效）
print("=" * 20, "zzhx login platform_hacked", "=" * 20)
try:
    c = MBBSClient(TARGETS["platform_hacked"], CFG["username"], CFG["password"])
    ok = c.login(max_attempts=8)
    if ok:
        me = c.me() or {}
        report["platform_hacked"]["zzhx_login"] = {
            "ok": True, "id": me.get("id"), "username": me.get("username"),
            "group": (me.get("group") or {}).get("name"),
        }
        # 带登录态再读设置（若公开面被遮蔽）
        try:
            payload = c.get("setting/getAll")
            report["platform_hacked"]["authed_setting_getAll"] = payload.get("data")
        except Exception as e:
            report["platform_hacked"]["authed_setting_getAll"] = {"error": str(e)}
        print("[zzhx] 登录成功 id=%s group=%s" % (me.get("id"), (me.get("group") or {}).get("name")))
    else:
        report["platform_hacked"]["zzhx_login"] = {"ok": False}
        print("[zzhx] 登录失败（平台站无此账号或凭据不同）")
except Exception as e:
    report["platform_hacked"]["zzhx_login"] = {"error": str(e)}
    print("[zzhx] 异常:", e)

(OUT / "audit_stage2_settings.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage2_settings.json")

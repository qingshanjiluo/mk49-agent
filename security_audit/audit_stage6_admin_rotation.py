# -*- coding: utf-8 -*-
"""阶段6：站长身份定位 + 密码改面探测 + zzhx 弱口令轮换 + 自有站复查。
- 轮换前先备份 config.json；轮换后立即回写新密码。
- 只对操作者自己的 bot 账号 zzhx 操作。
"""
import json
import secrets
import string
import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbbs.client import MBBSClient, MBBSAPIError  # noqa: E402

CFG_PATH = ROOT / "config.json"
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
OLD_PASS = CFG["password"]
NEW_SITE = "https://forum.mk49.top"
OLD_SITE = "https://mk48by049.mbbs.cc"
OUT = Path(__file__).resolve().parent / "out"

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S")}

# ---------- 1. 站长身份：迁移公告帖 37007 作者 ----------
c_old = MBBSClient(OLD_SITE, CFG["username"], OLD_PASS)
if not c_old.login(max_attempts=8):
    sys.exit(2)
try:
    t = c_old.thread_detail(37007)
    u = (t or {}).get("user") or {}
    report["admin_account"] = {"thread": 37007, "user": {
        k: u.get(k) for k in ("id", "name", "username", "nickname",
                              "group", "created_at")}}
    print("[站长候选]", json.dumps(report["admin_account"], ensure_ascii=False, default=str))
except Exception as e:
    report["admin_account"] = {"error": str(e)[:300]}
    print("[站长候选] error:", e)

# ---------- 2. 密码改面探测（错误旧密码 → 错误信息暴露字段名） ----------
for label, cli in (("old_site", c_old),):
    for shape in (
        {"old_password": "definitely-wrong", "new_password": "Xx1234567890!"},
        {"oldPassword": "definitely-wrong", "newPassword": "Xx1234567890!"},
        {"password": "definitely-wrong", "new_password": "Xx1234567890!"},
    ):
        try:
            cli.post("users/changePassword", shape)
            report.setdefault("changePassword_shape", {})[label] = {
                "shape": shape, "result": "UNEXPECTED_OK"}
            print("[shape]", label, shape, "-> 意外成功（不应对错误旧密码成功）")
            break
        except MBBSAPIError as e:
            msg = str(e)[:200]
            print("[shape]", label, list(shape.keys()), "->", msg)
            report.setdefault("changePassword_shape", {})[label] = {
                "shape_keys": list(shape.keys()), "error": msg}
            if "旧密码" in msg or "不正确" in msg or "old" in msg.lower():
                report["changePassword_shape"][label]["confirmed"] = list(shape.keys())
                break
        time.sleep(0.5)

# ---------- 3. 轮换 zzhx 密码（两站同账号线，各自独立用户表） ----------
alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
new_pass = "".join(secrets.choice(alphabet) for _ in range(24))
confirmed = (report.get("changePassword_shape", {}).get("old_site", {})
             .get("confirmed"))
report["rotation"] = {"new_password_len": len(new_pass)}

if confirmed:
    body = dict(zip(confirmed, (OLD_PASS, new_pass)))
    for label, origin in (("old_site", OLD_SITE), ("new_site", NEW_SITE)):
        try:
            c = MBBSClient(origin, CFG["username"], OLD_PASS)
            if not c.login(max_attempts=8):
                report["rotation"][label] = "login_failed_before_rotate"
                continue
            c.post("users/changePassword", body)
            # 验证新密码可登录
            c2 = MBBSClient(origin, CFG["username"], new_pass)
            ok = c2.login(max_attempts=5)
            report["rotation"][label] = "rotated+verified" if ok else "rotated_but_verify_failed"
            print("[rotate] %s -> %s" % (label, report["rotation"][label]))
        except MBBSAPIError as e:
            report["rotation"][label] = {"error": str(e)[:300]}
            print("[rotate] %s FAILED: %s" % (label, str(e)[:200]))
        time.sleep(0.8)
    # 回写 config.json（先备份）
    if report["rotation"].get("new_site") == "rotated+verified":
        bak = CFG_PATH.with_suffix(".json.bak-" + time.strftime("%Y%m%d%H%M%S"))
        shutil.copy2(CFG_PATH, bak)
        CFG["password"] = new_pass
        CFG_PATH.write_text(json.dumps(CFG, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        report["rotation"]["config_updated"] = True
        print("[config] 已回写新密码，备份:", bak.name)
else:
    report["rotation"]["skipped"] = "字段形状未确认，未执行轮换"
    print("[rotate] 跳过：字段形状未确认")

# ---------- 4. 自有站设置面匿名可读性复查 ----------
import requests
s = requests.Session()
s.trust_env = False
try:
    r = s.get(NEW_SITE + "/bbs/setting/getAll", timeout=15,
              headers={"User-Agent": "Mozilla/5.0", "Origin": NEW_SITE})
    j = r.json()
    d = j.get("data") or {}
    keys = {k: d.get(k) for k in ("site_name", "site_introduction",
                                  "site_keywords", "ui_power_by_text",
                                  "site_custom_append_head_html",
                                  "site_custom_append_body_html",
                                  "register_validate", "create_thread_validate",
                                  "site_enable_third_platform_login")}
    report["new_site_settings"] = keys
    print("[new_site]", json.dumps(keys, ensure_ascii=False, indent=1)[:1200])
except Exception as e:
    report["new_site_settings"] = {"error": str(e)[:300]}
    print("[new_site] error:", e)

# zzhx 在自有站尝试写设置（应被拒）
try:
    c3 = MBBSClient(NEW_SITE, CFG["username"],
                    new_pass if report["rotation"].get("new_site") == "rotated+verified" else OLD_PASS)
    c3.login(max_attempts=5)
    c3.post("setting/set", {"key": "site_name", "value": "audit-probe"})
    report["new_site_perm"] = "UNEXPECTED_WRITABLE"
except MBBSAPIError as e:
    report["new_site_perm"] = {"denied": str(e)[:120]}
    print("[new_site_perm] 拒绝（正常）:", str(e)[:100])

(OUT / "audit_stage6_admin_rotation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage6_admin_rotation.json")

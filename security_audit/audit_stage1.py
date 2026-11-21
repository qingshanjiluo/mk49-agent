# -*- coding: utf-8 -*-
"""mbbs.cc 被黑事件安全审计脚本（forum.mk49.top / 平台 mbbs.cc）

阶段1：登录 → 账号身份与权限 → 全分类清点 → 帖子/用户面垃圾内容扫描
只读操作：仅 GET 类接口 + 登录。删除/修改动作单独执行。
"""
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbbs.client import MBBSClient, MBBSAPIError, MBBSAuthError  # noqa: E402

import yaml  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(exist_ok=True)

SPAM_PATTERNS = [
    r"赌博", r"博彩", r"网赚", r"菠菜", r"皇冠", r"威尼斯", r"澳门", r"新葡京",
    r"百家乐", r"六合彩", r"时时彩", r"北京赛车", r"快三", r"德州扑克",
    r"代理返佣", r"日结", r"佣金", r"高薪招聘", r"兼职",
    r"色情", r"约炮", r"裸聊", r"援交", r"嫖",
    r"代开发票", r"发票", r"外挂", r"私服", r"传奇",
    r"贷款", r"提额", r"套现", r"币", r"代充", r"卡密",
    r"vi[pP]\d{3}", r"\.cc/", r"t\.cn/", r"bit\.ly",
]
SPAM_RE = re.compile("|".join(SPAM_PATTERNS), re.I)

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": []}


def step(name, data):
    report["steps"].append({"name": name, "data": data})
    print("=" * 30, name, "=" * 30)
    print(json.dumps(data, ensure_ascii=False, indent=1, default=str)[:6000])


def main():
    # 凭据：config.json 优先，补 .credentials.yaml
    username, password = CFG.get("username", ""), CFG.get("password", "")
    cred_file = ROOT / CFG.get("credential_file", ".credentials.yaml")
    if cred_file.exists():
        try:
            creds = yaml.safe_load(cred_file.read_text(encoding="utf-8")) or {}
            if isinstance(creds, dict):
                mb = creds.get("mbbs") or creds
                username = mb.get("username") or username
                password = mb.get("password") or password
        except Exception as e:
            print("[creds] parse failed:", e)
    print("[creds] user=%s pass_len=%d" % (username, len(password or "")))

    c = MBBSClient(CFG["base_url"], username, password)
    if not c.login(max_attempts=15):
        print("[FATAL] login failed")
        sys.exit(2)
    step("login", {"user": c.user})

    me = c.me()
    step("me", me)

    # 权限面
    try:
        perms = c.user_permissions((me or {}).get("group_id"))
        step("permissions", perms)
    except Exception as e:
        step("permissions", {"error": str(e)})

    # 分类清点
    cats = c.categories()
    step("categories", [{"id": x.get("id"), "name": x.get("name")} for x in cats])

    # 全分类帖子扫描（每分类前 50 条 × 最新排序 + 关键词检索）
    suspicious = []
    for cat in cats:
        cid = cat.get("id")
        try:
            threads, total = c.list_threads(category_id=cid, page_limit=50,
                                            sort="-created_at")
        except Exception as e:
            step("threads_cat_%s" % cid, {"error": str(e)})
            continue
        for t in threads:
            text = " ".join(str(t.get(k, "")) for k in ("title", "summary", "content"))
            m = SPAM_RE.search(text)
            if m:
                suspicious.append({
                    "thread_id": t.get("id"), "category": cat.get("name"),
                    "title": t.get("title"), "user": (t.get("user") or {}).get("name"),
                    "user_id": (t.get("user") or {}).get("id"),
                    "created_at": t.get("created_at"), "hit": m.group(0),
                })
    step("suspicious_threads", {"count": len(suspicious), "list": suspicious})

    # 关键词全站检索（服务端搜索接口）
    kw_hits = []
    for kw in ["博彩", "棋牌", "裸聊", "代开发票", "上门", "兼职", "信誉", "娱乐"]:
        try:
            threads, total = c.list_threads(keywords=kw, page_limit=20,
                                            sort="-created_at")
            for t in threads:
                kw_hits.append({"kw": kw, "thread_id": t.get("id"),
                                "title": t.get("title"),
                                "user": (t.get("user") or {}).get("name"),
                                "user_id": (t.get("user") or {}).get("id"),
                                "created_at": t.get("created_at")})
        except Exception as e:
            kw_hits.append({"kw": kw, "error": str(e)})
    step("keyword_search", {"count": len(kw_hits), "list": kw_hits})

    # 最新注册用户（垃圾注册水军）
    try:
        users, total = c.list_users(page_limit=50)
        step("latest_users", {"total": total,
                              "list": [{"id": u.get("id"), "name": u.get("name"),
                                        "created_at": u.get("created_at"),
                                        "group": u.get("group_id")} for u in users]})
    except Exception as e:
        step("latest_users", {"error": str(e)})

    # 站点设置（管理面可读部分）
    for path in ("settings/getSettings", "settings/list", "site/getSettings"):
        try:
            data = c.get(path)
            step("settings:%s" % path, data)
            break
        except Exception as e:
            continue

    (OUT_DIR / "audit_stage1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    print("[saved]", OUT_DIR / "audit_stage1.json")


if __name__ == "__main__":
    main()

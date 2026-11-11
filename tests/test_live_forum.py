"""Live integration smoke test against mk49.top (read-mostly).

Creates and deletes one throwaway thread to prove end-to-end capability:
login -> thread -> comment -> nested reply -> like -> upload -> delete.

Run:  python tests/test_live_forum.py
Skips entirely when LOGIN_SMOKE=0.
"""
import io
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import json

from mbbs.client import MBBSClient, MBBSAPIError
from mk49.config import load_config

MARK = "[smoke]"


def main():
    if os.getenv("LOGIN_SMOKE") == "0":
        print("SKIP: LOGIN_SMOKE=0")
        return 0
    cfg = load_config()
    c = MBBSClient(cfg["base_url"], cfg["username"], cfg["password"])
    results = []

    def check(name, fn, expect=True):
        try:
            val = fn()
            ok = bool(val) == bool(expect)
            results.append((name, ok, val))
            print(("PASS" if ok else "FAIL"), name, "->", str(val)[:120])
        except MBBSAPIError as exc:
            results.append((name, False, str(exc)))
            print("FAIL", name, "->", exc)

    check("login", c.ensure_login, True)
    if not c.token:
        print("cannot continue without login")
        return 1

    check("me", lambda: (c.me() or {}).get("username"), cfg["username"])
    check("categories", lambda: len(c.categories()) > 0)
    check("emojis", lambda: len(c.emojis()) > 0)
    check("list_threads", lambda: len(c.list_threads(page_limit=3)[0]) > 0)

    tid = pid = None

    def create():
        nonlocal tid
        d = c.create_thread(2, "%s 自动化冒烟测试 %s" % (MARK, os.getpid()),
                            "<p>%s 占位帖，稍后自删。</p>" % MARK)
        tid = (d or {}).get("id")
        return tid

    check("create_thread", create)
    if not tid:
        return finish(results)

    def comment():
        nonlocal pid
        d = c.create_post(tid, "<p>%s 一级评论</p>" % MARK)
        pid = (d or {}).get("id")
        return pid

    check("create_comment", comment)
    check("nested_reply",
          lambda: (c.reply_comment(pid, "<p>%s 嵌套回复</p>" % MARK) or {}).get("id"))
    check("like_thread", lambda: c.like_thread(tid, True))
    check("like_post", lambda: c.like_post(pid, True))

    def upload():
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (10, 150, 220)).save(buf, format="PNG")
        d = c.upload_resource(buf.getvalue(), "smoke.png", "image/png")
        path = (d or {}).get("filePath")
        return path and c.abs_resource_url(path).startswith("https://")

    check("upload_resource", upload)
    check("thread_detail", lambda: (c.thread_detail(tid) or {}).get("id") == tid)
    check("all_comments", lambda: len(c.all_comments(tid)) >= 2)
    check("list_drafts", lambda: isinstance(c.list_drafts()[0], list))
    check("polls_read", lambda: isinstance(c.polls_of_thread(48248), list))
    check("unread_count", lambda: c.unread_count() >= 0)
    check("resolve_cards", lambda: bool(c.resolve_cards(thread_ids=[48248])))
    check("delete_thread", lambda: c.delete_thread(tid))

    return finish(results)


def finish(results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("\n%d/%d live checks passed" % (passed, total))
    out = {
        "total": total,
        "passed": passed,
        "failed": [n for n, ok, _ in results if not ok],
    }
    pathlib.Path("state").mkdir(exist_ok=True)
    with open("state/live_test_report.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

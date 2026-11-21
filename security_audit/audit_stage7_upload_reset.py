# -*- coding: utf-8 -*-
"""阶段7：上传接口扩展名校验探测（无害）+ 站长密码重置链路探测。
- 上传只用"纯文本、无任何可执行标签"的内容，仅探测扩展名/Content-Type 是否被白名单过滤。
- 绝不提交可执行脚本；这是安全测试取证，不是利用。
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

report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "upload_tests": [],
          "reset_probes": []}

c = MBBSClient(ORIGIN, CFG["username"], CFG["password"])
if not c.login(max_attempts=8):
    sys.exit(2)

# ---------- 1. 上传接口扩展名/类型校验探测（无害纯文本） ----------
probe_contents = {
    "probe.png": "PNG-plain-text-ok",          # 正常图片扩展名（对照）
    "probe.html": "<plain-text-no-tags>",      # 扩展名 html，内容无标签
    "probe.php": "plain text only no code",    # 扩展名 php，内容无 PHP 标签
    "probe.txt": "plain text only",            # 正常文本
}
for fname, content in probe_contents.items():
    data = content.encode("utf-8")
    mime = "text/plain"
    try:
        resp = c.upload_resource(data, fname, mime)
        path = (resp or {}).get("path") or (resp or {}).get("file_path") or str(resp)
        url = c.abs_resource_url(path)
        report["upload_tests"].append({"file": fname, "accepted": True,
                                       "path": path, "url": url})
        print("[upload] %-14s ACCEPTED  url=%s" % (fname, url))
        # 校验落点内容是否被改写（若服务器按类型处理会改内容）
        try:
            import requests
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            report["upload_tests"][-1]["served_content"] = r.text[:200]
            report["upload_tests"][-1]["served_status"] = r.status_code
            print("         served[%s]: %s" % (r.status_code, r.text[:120]))
        except Exception as e:
            report["upload_tests"][-1]["fetch_error"] = str(e)[:120]
    except MBBSAPIError as e:
        report["upload_tests"].append({"file": fname, "accepted": False,
                                       "message": str(e)[:200], "status": e.status})
        print("[upload] %-14s REJECTED: %s" % (fname, str(e)[:120]))
    except Exception as e:
        report["upload_tests"].append({"file": fname, "accepted": False,
                                       "error": str(e)[:200]})
        print("[upload] %-14s ERROR: %s" % (fname, str(e)[:120]))
    time.sleep(0.6)

# ---------- 2. 站长 admin 密码重置链路探测（无操作，仅探参数形状） ----------
for path, body in [
    ("login/sendResetPasswordEmailVerifyCode", {"email": ""}),
    ("login/sendResetPasswordEmailVerifyCode", {"username": "admin"}),
    ("login/resetPasswordByBindEmail", {"email": "", "verify_code": "", "new_password": ""}),
]:
    try:
        r = c.post(path, body)
        report["reset_probes"].append({"path": path, "body": body, "resp": r})
        print("[reset] %s %s -> %s" % (path, json.dumps(body, ensure_ascii=False),
                                       json.dumps(r, ensure_ascii=False)[:300]))
    except MBBSAPIError as e:
        report["reset_probes"].append({"path": path, "body": body,
                                       "status": e.status, "msg": str(e)[:300],
                                       "payload": e.payload})
        print("[reset] %s %s -> DENIED(%s) %s" % (
            path, list(body.keys()), e.status, str(e)[:160]))
    except Exception as e:
        report["reset_probes"].append({"path": path, "error": str(e)[:200]})
    time.sleep(0.6)

(OUT / "audit_stage7_upload_reset.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("[saved]", OUT / "audit_stage7_upload_reset.json")
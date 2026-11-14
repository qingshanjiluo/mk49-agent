"""Web dashboard: live status, action stream and memory visualization.

Zero-dependency HTTP server (stdlib only) serving the embedded single-page
dashboard and JSON APIs that read agent_state.json + loop.log.

  python run.py dashboard        # http://127.0.0.1:8899
"""

import io
import json
import os
import time
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_PATH = os.path.join(ROOT, "state", "agent_state.json")
LOOP_LOG = os.path.join(ROOT, "state", "loop.log")
HTML_PATH = os.path.join(HERE, "dashboard.html")
PORT = int(os.getenv("MK49_DASH_PORT", "8899"))


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def loop_tail(n=60):
    try:
        with open(LOOP_LOG, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return "(loop.log not found)"


def is_alive(state):
    log = state.get("action_log") or []
    if not log:
        return False
    return time.time() - log[-1].get("ts", 0) < 3600  # active within 1h


def api_state(st):
    stats = st.get("stats", {})
    daily = st.get("daily", {})
    today = daily.get(datetime.now().strftime("%Y-%m-%d"), {})
    cfg = {}
    try:
        with open(os.path.join(ROOT, "config.json"), "r",
                  encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        pass
    kb = st.get("topic_heat", {})
    return {
        "alive": is_alive(st),
        "quiet": _quiet(cfg),
        "stats": stats,
        "today": today,
        "limits": {
            "threads": cfg.get("daily_post_limit", 2),
            "comments": cfg.get("daily_comment_limit", 8),
            "likes": 15,
        },
        "knowledge_items": len(kb) or _knowledge_count(),
        "mem_threads": len(st.get("thread_memory", {})),
        "mem_users": len(st.get("user_memory", {})),
        "notes": len(st.get("notes", [])),
    }


def _quiet(cfg):
    start = int(cfg.get("quiet_start", 23))
    end = int(cfg.get("quiet_end", 8))
    hour = datetime.now().hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _knowledge_count():
    try:
        with open(os.path.join(ROOT, "state", "knowledge.json"), "r",
                  encoding="utf-8") as fh:
            return len(json.load(fh).get("items", []))
    except (OSError, ValueError):
        return 0


def api_log(st, since):
    items = [x for x in (st.get("action_log") or []) if x.get("seq", 0) > since]
    out = []
    for i, x in enumerate(items):
        out.append({"seq": x.get("seq", 0), "ts": x.get("ts", 0),
                    "action": x.get("action", ""),
                    "detail": x.get("detail", "")})
    last = st.get("log_seq", 0)
    if out:
        last = out[-1]["seq"]
    return {"items": out, "last": last}


def api_memory(st):
    kb_md = ""
    try:
        with open(os.path.join(ROOT, "state", "knowledge.md"), "r",
                  encoding="utf-8", errors="replace") as fh:
            kb_md = fh.read()
    except OSError:
        pass
    knowledge = _md_to_html(kb_md)

    threads = []
    for tid, entries in list((st.get("thread_memory") or {}).items())[-15:]:
        rows = [{"who": ("我" if e.get("kind") == "mine" else e.get("who", "对方")),
                 "text": e.get("text", "")} for e in entries[-6:]]
        threads.append({"tid": tid, "entries": rows})

    users = []
    for uid, u in list((st.get("user_memory") or {}).items())[-20:]:
        users.append({"uid": uid, "nick": u.get("nick", ""),
                      "n": u.get("n", 0)})

    now = time.time()
    queue = [{"note": it.get("note", ""),
              "due_in_s": max(0, int(it.get("run_at", 0) - now)),
              "steps": len((it.get("payload") or {}).get("script", []))}
             for it in (st.get("workflow_queue") or [])]

    return {
        "knowledge": knowledge or "",
        "threads": threads,
        "users": users,
        "notes": list(reversed((st.get("notes") or [])))[:30],
        "diary": list(reversed((st.get("memory_log") or [])))[:30],
        "queue": queue,
    }


def _md_to_html(md):
    """Tiny markdown subset -> HTML lines (headings, bullets, bold)."""
    import re
    out = []
    for line in (md or "").splitlines():
        ln = escape(line)
        ln = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", ln)
        if ln.startswith("## "):
            out.append("<div style='color:#58a6ff;margin-top:6px'><b>%s</b></div>"
                       % ln[3:])
        elif ln.startswith("- "):
            out.append("<div class='mem-item'>• %s</div>" % ln[2:])
        elif ln.startswith("#"):
            continue
        elif ln.strip():
            out.append("<div>%s</div>" % ln)
    return "".join(out)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep quiet

    def _send(self, code, ctype, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        st = load_state()
        try:
            if path == "/" or path == "/index.html":
                with open(HTML_PATH, "r", encoding="utf-8") as fh:
                    self._send(200, "text/html; charset=utf-8", fh.read())
            elif path == "/api/state":
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(api_state(st), ensure_ascii=False))
            elif path == "/api/log":
                qs = parse_qs(parsed.query)
                since = int((qs.get("since") or ["0"])[0] or 0)
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(api_log(st, since), ensure_ascii=False))
            elif path == "/api/memory":
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(api_memory(st), ensure_ascii=False))
            elif path == "/api/console":
                self._send(200, "application/json; charset=utf-8",
                           json.dumps({"text": loop_tail(80)},
                                      ensure_ascii=False))
            else:
                self._send(404, "text/plain", "not found")
        except Exception as exc:
            self._send(500, "text/plain", "error: %s" % exc)


def serve(port=None):
    port = port or PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("[dashboard] http://127.0.0.1:%d  (ctrl+c to stop)" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()

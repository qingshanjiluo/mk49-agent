"""Forum-integrated chat tools (/bbs/chat/*, live-verified 2026-11-21).

Conversations: 1 = lobby 大厅 (channel 1 综合), other ids = private DMs.
Rate limit: 429 + Retry-After header, body "此群发送过快，请稍后再发".
Send pacing: <=4 msgs/sec then forced wait; _send() always honors 429."""
import time
import uuid

import requests

from .base import Tool, schema, jdump

CHAT_BASE = "https://forum.mk49.top/bbs/chat"
S = requests.Session()
S.trust_env = False
S.headers["User-Agent"] = "Mozilla/5.0"

_last_send = [0.0]
MIN_SEND_GAP = 1.3   # seconds between sends (server trips at ~4 quick)


def _req(method, token, path, body=None, files=None, timeout=40,
         tries=3, gap=True):
    """Authenticated chat call honoring 429/Retry-After + min send gap."""
    url = CHAT_BASE + "/" + path.lstrip("/")
    H = {"authorization": token, "User-Agent": "Mozilla/5.0"}
    last = {"status": -1, "ms": 0, "ra": None, "data": None}
    for attempt in range(max(1, tries)):
        if gap and method.upper() == "POST":
            wait = MIN_SEND_GAP - (time.time() - _last_send[0])
            if wait > 0:
                time.sleep(wait)
        t0 = time.time()
        try:
            if body is None and files is None:
                r = S.request(method, url, headers=H, timeout=timeout)
            elif files:
                r = S.request(method, url, headers=H, data=body or {},
                               files=files, timeout=timeout)
            else:
                hh = dict(H)
                hh["Content-Type"] = "application/json"
                r = S.request(method, url, headers=hh, json=body, timeout=timeout)
        except Exception as exc:
            last = {"status": -1, "ms": int((time.time() - t0) * 1000),
                    "ra": None, "data": {"error": str(exc)[:120]}}
            time.sleep(1.0)
            continue
        if method.upper() == "POST":
            _last_send[0] = time.time()
        ms = int((time.time() - t0) * 1000)
        ra = r.headers.get("Retry-After")
        try:
            d = r.json()
        except Exception:
            d = {"raw": r.text[:160]}
        last = {"status": r.status_code, "ms": ms, "ra": ra, "data": d}
        if r.status_code == 429:
            time.sleep(int(ra or 1) + 0.4)
            continue
        return last
    return last


def _wrap(res, action=""):
    d = res.get("data") or {}
    ok = res.get("status") == 200 and d.get("success") is not False
    return jdump({"ok": ok, "status": res.get("status"),
                  "ms": res.get("ms"),
                  "retry_after": res.get("ra"),
                  "action": action,
                  "data": d.get("data") if isinstance(d, dict) else d,
                  "error": None if ok else ((d.get("message")
                                             if isinstance(d, dict)
                                             else None) or str(d)[:160])})


def _msg_row(m):
    row = {"id": m.get("id"),
           "who": m.get("sender_name") or m.get("sender_id"),
           "time": m.get("created_at"),
           "text": (m.get("body") or "")[:180]}
    if m.get("reply_id"):
        row["reply_to"] = {"id": m.get("reply_id"),
                           "who": m.get("reply_sender_name"),
                           "text": (m.get("reply_body") or "")[:80]}
    if m.get("has_image"):
        row["image"] = True
    if m.get("deleted_at"):
        row["deleted"] = True
    return row


class ChatList(Tool):
    name = "chat_conversations"
    description = ("List chat conversations: lobby groups and private DMs "
                   "(peer names + unread).")
    params = schema({}, required=[])
    max_result = 2500

    def run(self, agent):
        r = _req("GET", agent.client.token, "conversations")
        d = (r.get("data") or {}).get("data") or {}
        items = d.get("items") if isinstance(d, dict) else (d or [])
        out = []
        for c in items or []:
            out.append({
                "id": c.get("id"),
                "kind": "lobby" if c.get("is_lobby") else "dm",
                "title": c.get("title") or ("%s ↔ %s" % (
                    c.get("owner_name") or "?", c.get("peer_name") or "?")),
                "unread": c.get("unread"),
                "activity": c.get("activity"),
                "blocked": c.get("blocked"),
            })
        return "total=%d\n%s" % (len(out), jdump(out))


class ChatRead(Tool):
    name = "chat_read"
    description = ("Read chat messages from a conversation (lobby with "
                   "channel, or private DM). Returns newest-first with "
                   "reply_to context.")
    params = schema({"converse_id": ("integer",
                    "1=大厅 lobby, other=DM id (see chat_conversations)"),
                     "channel": ("integer",
                                 "lobby channel id, default 1 (综合); "
                                 "omit for DM"),
                     "limit": ("integer", "max messages, default 20")},
                    required=["converse_id"])
    max_result = 5000

    def run(self, agent, converse_id=1, channel=None, limit=20):
        cid = int(converse_id)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages" % cid
        if ch:
            path += "?channel=%d" % ch
        r = _req("GET", agent.client.token, path, gap=False)
        d = (r.get("data") or {}).get("data") or {}
        items = d.get("items") or [] if isinstance(d, dict) else []
        rows = [_msg_row(m) for m in items[: max(1, int(limit or 20))]]
        return "conv=%d ch=%s msgs=%d\n%s" % (cid, ch, len(rows), jdump(rows))


class ChatSend(Tool):
    name = "chat_send"
    description = ("Send a chat message (lobby or DM). Auto-handles "
                   "429/Retry-After rate limit. style: casual short text.")
    params = schema({"converse_id": ("integer", "conversation id (1=lobby)"),
                     "text": ("string", "message body"),
                     "channel": ("integer", "channel id (lobby, default 1)")},
                    required=["converse_id", "text"])
    danger = True
    max_result = 1500

    def run(self, agent, converse_id=1, text="", channel=None):
        cid = int(converse_id)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages" % cid
        if ch:
            path += "?channel=%d" % ch
        body = {"body": str(text)[:900], "clientId": uuid.uuid4().hex}
        r = _req("POST", agent.client.token, path, body=body)
        d = (r.get("data") or {}).get("data") or {}
        ok = r.get("status") == 200 and isinstance(d, dict) and d.get("id")
        if ok:
            agent.state.log("chat_send", "conv=%d msg=%s" % (cid, d.get("id")))
        return _wrap(r, "chat_send conv=%d" % cid)


class ChatReply(Tool):
    name = "chat_reply"
    description = ("Reply to a specific chat message (quoted reply, "
                   "replyTo field). Auto-handles rate limit.")
    params = schema({"converse_id": ("integer", "conversation id (1=lobby)"),
                     "message_id": ("integer", "target message id to quote"),
                     "text": ("string", "reply body"),
                     "channel": ("integer", "channel id (lobby, default 1)")},
                    required=["converse_id", "message_id", "text"])
    danger = True
    max_result = 1500

    def run(self, agent, converse_id=1, message_id=0, text="", channel=None):
        cid = int(converse_id)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages" % cid
        if ch:
            path += "?channel=%d" % ch
        body = {"body": str(text)[:900], "clientId": uuid.uuid4().hex,
                "replyTo": int(message_id)}
        r = _req("POST", agent.client.token, path, body=body)
        d = (r.get("data") or {}).get("data") or {}
        if r.get("status") == 200 and isinstance(d, dict) and d.get("id"):
            agent.state.log("chat_reply", "conv=%d reply=%s->%s"
                            % (cid, message_id, d.get("id")))
        return _wrap(r, "chat_reply conv=%d -> msg %s" % (cid, message_id))


class ChatSendImage(Tool):
    name = "chat_send_image"
    description = ("Send an image into chat (multipart file upload, up to "
                   "2MB). Use generated or cached local image path.")
    params = schema({"converse_id": ("integer", "conversation id (1=lobby)"),
                     "file_path": ("string", "local image path"),
                     "text": ("string", "caption (optional)"),
                     "channel": ("integer", "channel id (lobby, default 1)")},
                    required=["converse_id", "file_path"])
    danger = True
    max_result = 1500

    def run(self, agent, converse_id=1, file_path="", text="", channel=None):
        import os
        if not file_path or not os.path.exists(file_path):
            return "ERROR: file not found: %s" % file_path
        if os.path.getsize(file_path) > 2 * 1024 * 1024:
            return "ERROR: >2MB (compress first, e.g. fit_for_forum)"
        cid = int(converse_id)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages" % cid
        if ch:
            path += "?channel=%d" % ch
        data = {"body": str(text or "图")[:200],
                "clientId": uuid.uuid4().hex}
        fname = os.path.basename(file_path)
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "jpg").lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        r = _req("POST", agent.client.token, path, body=data,
                 files={"file": (fname, open(file_path, "rb"), mime)},
                 timeout=120)
        d = (r.get("data") or {}).get("data") or {}
        if r.get("status") == 200 and isinstance(d, dict) and d.get("id"):
            agent.state.log("chat_image", "conv=%d msg=%s" % (cid, d.get("id")))
        return _wrap(r, "chat_send_image conv=%d" % cid)


class ChatOpenDM(Tool):
    name = "chat_open_dm"
    description = ("Open (or find) a private conversation with a forum user "
                   "by userId; returns converse_id for chat_send/read.")
    params = schema({"user_id": ("integer", "target forum user id")},
                    required=["user_id"])
    max_result = 1500

    def run(self, agent, user_id=0):
        if int(user_id) == int(agent.client.user_id):
            return "ERROR: 不能给自己发私聊"
        r = _req("POST", agent.client.token, "direct",
                 body={"userId": int(user_id)})
        return _wrap(r, "chat_open_dm user=%s" % user_id)


class ChatUnread(Tool):
    name = "chat_unread"
    description = "Unread chat counters (messages + invitations)."
    params = schema({}, required=[])

    def run(self, agent):
        r = _req("GET", agent.client.token, "unread", gap=False)
        return _wrap(r, "chat_unread")


class ChatRemove(Tool):
    name = "chat_remove"
    description = "Delete one of my chat messages (cleanup of test output)."
    params = schema({"converse_id": ("integer", "conversation id"),
                     "message_id": ("integer", "my message id to remove"),
                     "channel": ("integer", "channel id (lobby, default 1)")},
                    required=["converse_id", "message_id"])
    danger = True
    max_result = 1200

    def run(self, agent, converse_id=1, message_id=0, channel=None):
        cid = int(converse_id)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages/%s/remove" % (cid, message_id)
        if ch:
            path += "?channel=%d" % ch
        r = _req("POST", agent.client.token, path, body={}, gap=False)
        return _wrap(r, "chat_remove msg=%s" % message_id)


def register_all(reg):
    for t in (ChatList(), ChatRead(), ChatSend(), ChatReply(),
              ChatSendImage(), ChatOpenDM(), ChatUnread(), ChatRemove()):
        reg.register(t)

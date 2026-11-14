"""Interaction memory: what we said, what they said, per thread and user.

Gives the agent continuity - it can avoid repeating itself, recognize people
it talked to, and keep a daily diary of its forum life.
"""

import time
from datetime import date

from mbbs.content import truncate, strip_html

MAX_THREADS = 300
MAX_ENTRIES_PER_THREAD = 12
MAX_USERS = 500


class InteractionMemory:
    def __init__(self, state):
        self.state = state
        data = state.data
        data.setdefault("thread_memory", {})   # tid -> [entries]
        data.setdefault("user_memory", {})     # uid -> {nick, n, last}
        data.setdefault("memory_log", [])      # daily diary lines

    # ---------------- threads ----------------
    def record_reply(self, thread_id, my_post_id, my_text):
        tid = str(thread_id)
        seq = self.state.data["thread_memory"].setdefault(tid, [])
        seq.append({"ts": time.time(),
                    "kind": "mine",
                    "post_id": my_post_id,
                    "text": truncate(strip_html(my_text), 160)})
        self._trim(tid)

    def record_their_reply(self, thread_id, post_id, who, uid, text):
        tid = str(thread_id)
        seq = self.state.data["thread_memory"].setdefault(tid, [])
        seq.append({"ts": time.time(),
                    "kind": "theirs",
                    "post_id": post_id,
                    "who": truncate(str(who), 24),
                    "uid": uid,
                    "text": truncate(strip_html(text), 160)})
        self._trim(tid)

    def _trim(self, tid):
        seq = self.state.data["thread_memory"][tid]
        if len(seq) > MAX_ENTRIES_PER_THREAD:
            del seq[: len(seq) - MAX_ENTRIES_PER_THREAD]
        threads = self.state.data["thread_memory"]
        if len(threads) > MAX_THREADS:
            for old in sorted(threads, key=lambda k: threads[k][0]["ts"]
                              if threads[k] else 0)[: len(threads) - MAX_THREADS]:
                del threads[old]

    def thread_context(self, thread_id, limit=4):
        """Compact 'what happened here before' block for prompts."""
        seq = self.state.data["thread_memory"].get(str(thread_id)) or []
        if not seq:
            return ""
        rows = []
        for e in seq[-limit:]:
            who = "我" if e["kind"] == "mine" else e.get("who", "对方")
            rows.append("- %s：%s" % (who, e.get("text", "")))
        return "本帖此前的互动记忆：\n" + "\n".join(rows)

    def replied_posts(self):
        """Post ids we already answered (dedupe guard)."""
        out = set()
        for seq in self.state.data["thread_memory"].values():
            for e in seq:
                if e["kind"] == "mine" and e.get("post_id"):
                    out.add(str(e["post_id"]))
        return out

    # ---------------- users ----------------
    def touch_user(self, uid, nick):
        if not uid:
            return
        users = self.state.data["user_memory"]
        rec = users.setdefault(str(uid), {"nick": "", "n": 0, "last": 0})
        if nick:
            rec["nick"] = truncate(str(nick), 24)
        rec["n"] = int(rec.get("n", 0)) + 1
        rec["last"] = time.time()
        if len(users) > MAX_USERS:
            for old in sorted(users, key=lambda k: users[k].get("last", 0))[
                   : len(users) - MAX_USERS]:
                del users[old]

    def known_user(self, uid):
        return self.state.data["user_memory"].get(str(uid))

    # ---------------- diary ----------------
    def daily_summary(self, stats, topics):
        line = "%s | comments=%s likes=%s threads=%s | hot: %s" % (
            date.today().isoformat(),
            stats.get("comments", 0), stats.get("likes", 0),
            stats.get("threads", 0), "、".join(topics[:5]))
        log = self.state.data["memory_log"]
        if not log or log[-1].split(" | ")[0] != line.split(" | ")[0]:
            log.append(line)
            if len(log) > 180:
                del log[: len(log) - 180]

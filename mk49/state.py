"""Persistent agent state (processed ids, counters, quotas, action log)."""

import json
import os
import threading
import time
from datetime import date


class State:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {
            "processed_threads": [],
            "processed_posts": [],
            "my_threads": [],
            "my_posts": [],
            "liked_threads": [],
            "welcomed_users": [],
            "daily": {},          # {"2026-11-10": {"threads": n, "comments": n, ...}}
            "action_log": [],     # [{"ts", "action", "detail"}]
            "seen_messages": [],
            "stats": {"cycles": 0, "threads": 0, "comments": 0, "likes": 0,
                      "images": 0, "poll_votes": 0, "welcome": 0},
        }
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                if isinstance(saved, dict):
                    self.data.update(saved)
            except (OSError, ValueError) as exc:
                print("[state] load failed: %s" % exc)

    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    # ------- helpers -------
    @staticmethod
    def _bucket(seq, key, max_len=8000):
        return key in seq

    def seen_thread(self, tid):
        return str(tid) in self.data["processed_threads"]

    def mark_thread(self, tid):
        self._append("processed_threads", str(tid))

    def seen_post(self, pid):
        return str(pid) in self.data["processed_posts"]

    def mark_post(self, pid):
        self._append("processed_posts", str(pid))

    def _append(self, key, value):
        with self.lock:
            seq = self.data[key]
            if value not in seq:
                seq.append(value)
                if len(seq) > 8000:
                    del seq[: len(seq) - 8000]

    # ------- daily quotas -------
    def _today(self):
        return date.today().isoformat()

    def _day_bucket(self):
        day = self._today()
        bucket = self.data["daily"].get(day)
        if bucket is None:
            # prune old days
            self.data["daily"] = {day: {}}
            bucket = {}
            self.data["daily"][day] = bucket
        return bucket

    def daily_count(self, kind):
        return int(self._day_bucket().get(kind, 0))

    def bump_daily(self, kind, n=1):
        with self.lock:
            bucket = self._day_bucket()
            bucket[kind] = int(bucket.get(kind, 0)) + n

    def log(self, action, detail=""):
        with self.lock:
            self.data["action_log"].append(
                {"ts": time.time(), "action": action, "detail": str(detail)[:400]}
            )
            if len(self.data["action_log"]) > 3000:
                del self.data["action_log"][: len(self.data["action_log"]) - 3000]

    def recent_actions(self, n=20, action=None):
        seq = self.data["action_log"]
        if action:
            seq = [x for x in seq if x.get("action") == action]
        return seq[-n:]

    def stat_bump(self, key, n=1):
        with self.lock:
            stats = self.data.setdefault("stats", {})
            stats[key] = int(stats.get(key, 0)) + n

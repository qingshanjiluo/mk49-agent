"""Throttled autosave so the dashboard sees actions near-realtime."""
import io

P = "mk49/state.py"
s = io.open(P, encoding="utf-8").read()

old = """    def log(self, action, detail=""):
        with self.lock:
            self.data["action_log"].append(
                {"ts": time.time(), "action": action, "detail": str(detail)[:400]}
            )
            if len(self.data["action_log"]) > 3000:
                del self.data["action_log"][: len(self.data["action_log"]) - 3000]"""
new = """    def log(self, action, detail=""):
        with self.lock:
            self.data["action_log"].append(
                {"ts": time.time(), "action": action, "detail": str(detail)[:400]}
            )
            if len(self.data["action_log"]) > 3000:
                del self.data["action_log"][: len(self.data["action_log"]) - 3000]
        self.autosave()

    def autosave(self, min_interval=15.0):
        \"\"\"Persist at most every min_interval seconds (dashboard freshness).\"\"\"
        now = time.time()
        last = getattr(self, "_last_autosave", 0.0)
        if now - last < min_interval:
            return
        self._last_autosave = now
        try:
            self.save()
        except Exception:
            pass"""
assert old in s, "log anchor"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("autosave added")

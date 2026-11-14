"""Add seq counter to State.log for incremental dashboard polling."""
import io

P = "mk49/state.py"
s = io.open(P, encoding="utf-8").read()

old = """    def log(self, action, detail=""):
        with self.lock:
            self.data["action_log"].append(
                {"ts": time.time(), "action": action, "detail": str(detail)[:400]}
            )"""
new = """    def log(self, action, detail=""):
        with self.lock:
            seq = int(self.data.get("log_seq", 0)) + 1
            self.data["log_seq"] = seq
            self.data["action_log"].append(
                {"seq": seq, "ts": time.time(), "action": action,
                 "detail": str(detail)[:400]}
            )"""
assert old in s, "log seq anchor"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("seq added")

P2 = "run.py"
s2 = io.open(P2, encoding="utf-8").read()
old2 = """def cmd_learn():"""
new2 = """def cmd_dashboard():
    from mk49.dashboard import serve
    serve()
    return 0


def cmd_learn():"""
assert old2 in s2
s2 = s2.replace(old2, new2, 1)
old2 = '''        "learn": cmd_learn,'''
new2 = '''        "learn": cmd_learn,
        "dashboard": cmd_dashboard,'''
assert old2 in s2
s2 = s2.replace(old2, new2, 1)
io.open(P2, "w", encoding="utf-8", newline="\n").write(s2)
print("dashboard command added")

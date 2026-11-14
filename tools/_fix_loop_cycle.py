"""run_forever must go through run_cycle() (which now includes the master
tool-calling phase); the inline sequence predates that phase."""
import io

P = "mk49/agent.py"
s = io.open(P, encoding="utf-8").read()

old = """            wrote = []
            try:
                self.observe()
                plan = self.decide()
                wrote = self.act(plan)
                self.reflect(wrote)
            except Exception as exc:"""
new = """            wrote = []
            try:
                wrote = self.run_cycle()
            except Exception as exc:"""
assert old in s, "run_forever inline anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("run_forever now uses run_cycle")

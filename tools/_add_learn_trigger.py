import io

P = "mk49/agent.py"
s = io.open(P, encoding="utf-8").read()

if 'plan["learn"]' in s:
    print("learn trigger already present")
    raise SystemExit(0)

old = (
    '        else:\n'
    '            plan.setdefault("daily_digest", False)\n'
    "        return plan"
)
new = (
    '        else:\n'
    '            plan.setdefault("daily_digest", False)\n'
    "        # knowledge pass: once per day, any hour (read-only work)\n"
    '        plan["learn"] = self.state.daily_count("learn") == 0\n'
    "        return plan"
)
assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("learn trigger added")

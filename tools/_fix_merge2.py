import io

P = "mk49/knowledge.py"
s = io.open(P, encoding="utf-8").read()
old = "                added += len(self.kb.merge(items, max_items=120))"
new = "                added += self.kb.merge(items, max_items=120)"
assert old in s
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("fixed")

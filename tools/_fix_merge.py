import io

P = "mk49/knowledge.py"
s = io.open(P, encoding="utf-8").read()

# fix: merge extracted items into the KB (they were counted but never stored)
old = """                self.scan_format(t)
                added += len(self.extract_from_thread(t))
                scanned += 1"""
new = """                self.scan_format(t)
                items = self.extract_from_thread(t)
                added += len(self.kb.merge(items, max_items=120))
                scanned += 1"""
assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("merge fix applied")

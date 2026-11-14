"""Fuzzy alias resolution for LLM tool-name mistakes in dispatch."""
import difflib
import io

P = "mk49/tools/base.py"
s = io.open(P, encoding="utf-8").read()

old = """    def dispatch(self, agent, name, args):
        \"\"\"Execute a tool; returns a text result (never raises).\"\"\"
        tool = self._tools.get(name)
        if tool is None:
            return "ERROR: unknown tool %s" % name"""
new = """    def resolve(self, name):
        \"\"\"Exact hit, else closest tool name (LLMs sometimes guess).\"\"\"
        if name in self._tools:
            return self._tools[name]
        matches = difflib.get_close_matches(name, self._tools, n=1, cutoff=0.75)
        return self._tools[matches[0]] if matches else None

    def dispatch(self, agent, name, args):
        \"\"\"Execute a tool; returns a text result (never raises).\"\"\"
        tool = self.resolve(name)
        if tool is None:
            return "ERROR: unknown tool %s" % name
        if tool.name != name:
            agent.log("tool alias: %s -> %s" % (name, tool.name))"""
assert old in s, "dispatch anchor"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("alias resolution added")

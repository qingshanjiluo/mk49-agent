import io

P = "features/knowledge_learner.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("state.dally 'learn'", "state.daily 'learn'")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("typo fixed")

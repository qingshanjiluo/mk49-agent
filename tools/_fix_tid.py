"""Fix tid NameError in message_center._decide."""
import io

P = "features/message_center.py"
s = io.open(P, encoding="utf-8").read()
old = "prev_memory = agent.memory.thread_context(tid)"
new = 'prev_memory = agent.memory.thread_context(e["thread_id"])'
assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("tid fixed")

"""Bump chat_raw request timeout to 300s (tool-call prompts are slow)."""
import io

P = "mk49/llm.py"
s = io.open(P, encoding="utf-8").read()

old = ("                r = self.session.post(self.base_url + \"/chat/completions\",\n"
       "                                      headers=headers, json=payload,\n"
       "                                      timeout=self.timeout)\n"
       "                if r.status_code >= 400:\n"
       "                    raise LLMError(\"HTTP %s %s\"\n"
       "                                   % (r.status_code, r.text[:160]))\n"
       "                data = r.json()\n"
       "                if \"error\" in data:\n"
       "                    raise LLMError(str(data[\"error\"])[:200])\n"
       "                return data[\"choices\"][0][\"message\"] or {}")
new = ("                r = self.session.post(self.base_url + \"/chat/completions\",\n"
       "                                      headers=headers, json=payload,\n"
       "                                      timeout=max(self.timeout, 300))\n"
       "                if r.status_code >= 400:\n"
       "                    raise LLMError(\"HTTP %s %s\"\n"
       "                                   % (r.status_code, r.text[:160]))\n"
       "                data = r.json()\n"
       "                if \"error\" in data:\n"
       "                    raise LLMError(str(data[\"error\"])[:200])\n"
       "                return data[\"choices\"][0][\"message\"] or {}")
assert old in s, "chat_raw post anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("chat_raw timeout -> max(120,300)s")

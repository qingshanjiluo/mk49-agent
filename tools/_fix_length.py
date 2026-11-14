"""Soften length enforcement: let the LLM decide naturally, keep only a
generous hard cap; prompts get a per-call length dice for variety."""
import io

# ---------- style.py ----------
P = "mk49/style.py"
s = io.open(P, encoding="utf-8").read()

old = '''COMMENT_MAX = 150
COMMENT_TARGET = 60
POST_MAX = 500
POST_TARGET = 260'''
new = '''COMMENT_MAX = 200     # generous hard cap; the model picks its own length
POST_MAX = 500
POST_TARGET = 260
# natural length buckets a real member swings between
LENGTH_DICE = [
    ("超短", "3~12 个字，就像随手回一句（如 确实/哈哈这真的离谱/绷不住）"),
    ("短", "15~40 个字，一两句话接住对方的点"),
    ("中", "40~90 个字，补一点自己的经验或观点"),
]'''
assert old in s, "cap anchor"
s = s.replace(old, new, 1)

old = '''    def enforce_length(self, text, kind="comment", agent=None):
        """Regenerate shorter when way over target; hard-cut as last resort."""
        limit = self.comment_max if kind == "comment" else self.post_max
        target = COMMENT_TARGET if kind == "comment" else POST_TARGET
        if len(text) <= limit * 1.2:
            return self.humanize(text, kind)
        # one shorten round via LLM when available
        if agent is not None and getattr(agent, "llm", None):
            try:
                shorter = agent.llm.text(
                    "把下面的论坛发言压缩到 %d 字以内，保留原语气，只输出压缩后的正文：\\n%s"
                    % (target, text[:600]),
                    tier="fast", max_tokens=220, temperature=0.6,
                )
                if shorter and len(shorter) <= limit:
                    return self.humanize(shorter, kind)
            except Exception:
                pass
        return _sentence_cut(self.humanize(text, kind), limit)'''
new = '''    def enforce_length(self, text, kind="comment", agent=None):
        """Only guard against essay-length output; the model owns its length."""
        limit = self.comment_max if kind == "comment" else self.post_max
        if len(text) <= limit:
            return self.humanize(text, kind)
        # one shorten round only when way over the generous cap
        if agent is not None and getattr(agent, "llm", None):
            try:
                shorter = agent.llm.text(
                    "把下面的论坛发言压缩到 %d 字以内，保留原语气，只输出压缩后的正文：\\n%s"
                    % (COMMENT_TARGET, text[:600]),
                    tier="fast", max_tokens=220, temperature=0.6,
                )
                if shorter and len(shorter) <= limit:
                    return self.humanize(shorter, kind)
            except Exception:
                pass
        return _sentence_cut(self.humanize(text, kind), limit)

    def length_dice(self):
        """Random natural length bucket injected into prompts for variety."""
        import random
        return random.choice(LENGTH_DICE)'''
assert old in s, "enforce anchor"
s = s.replace(old, new, 1)

# length_hint update: stop pushing 60-char target
old = '''    def length_hint(self, kind="comment"):
        if kind == "comment":
            return "长度 15~%d 字，理想 %d 字上下；" % (self.comment_max,
                                                     COMMENT_TARGET)
        return "长度 %d~%d 字；" % (COMMENT_TARGET, self.post_max)'''
new = '''    def length_hint(self, kind="comment"):
        if kind == "comment":
            return ("长度自己看着定：真人回帖经常就 3~15 个字，偶尔才写长；"
                    "超过 120 字基本必是真人不写的；")
        return "长度 %d~%d 字；" % (COMMENT_TARGET, self.post_max)'''
assert old in s, "hint anchor"
s = s.replace(old, new, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("style.py: model-owned length + dice")

# ---------- llm.py prompts: natural length + dice ----------
P2 = "mk49/llm.py"
s2 = io.open(P2, encoding="utf-8").read()

old = '''            "任务：写一条回复这个帖子的评论。要求：\\n"
            "1. 40~150 字，口语自然，像真人玩家随口聊；\\n"'''
new = '''            "任务：写一条回复这个帖子的评论。要求：\\n"
            "1. 长度模仿真人：多数回帖就 3~30 字，想到什么说一句；"
            "只有真有干货值得展开才写长（最多 120 字）；\\n"'''
assert old in s2, "continue anchor"
s2 = s2.replace(old, new, 1)

old = '''            "任务：写一条直接回应这一楼的回复，30~120 字。要求：\\n"
            "1. 只接对方这句话里的具体点（他说的船/操作/观点/情绪），"
            "可以赞同、反驳、补充、玩梗或反问；\\n"'''
new = '''            "任务：写一条直接回应这一楼的回复。要求：\\n"
            "1. 长度像真人斗嘴：经常就几个字到 30 字（哈？/确实/这不扯吗），"
            "最多不超过 100 字；\\n"
            "2. 只接对方这句话里的具体点（他说的船/操作/观点/情绪），"
            "可以赞同、反驳、补充、玩梗或反问；\\n"'''
assert old in s2, "reply anchor"
s2 = s2.replace(old, new, 1)

io.open(P2, "w", encoding="utf-8", newline="\n").write(s2)
print("llm prompts: natural length")

# ---------- persona.txt ----------
P3 = "persona.txt"
s3 = io.open(P3, encoding="utf-8").read()
old = "- 评论长度铁律：15~80 字为主，硬上限 120 字；超过就砍到句子边界。"
new = ("- 评论长度自己定：真人大半回帖是 3~30 字的短句，长篇才显眼；"
       "有干货再写长，硬上限 120。")
if old in s3:
    s3 = s3.replace(old, new, 1)
    io.open(P3, "w", encoding="utf-8", newline="\n").write(s3)
    print("persona length rule updated")
else:
    print("persona length rule not found (skip)")

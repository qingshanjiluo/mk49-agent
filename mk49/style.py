"""Style skill: length control, tone shaping, AI-ism scrubbing.

Every outbound text passes through StyleSkill.humanize() so posts and
comments read like a real member: short, casual, no essay structure.
"""

import re

COMMENT_MAX = 200     # generous hard cap; the model picks its own length
POST_MAX = 500
POST_TARGET = 260
# natural length buckets a real member swings between
LENGTH_DICE = [
    ("超短", "3~12 个字，就像随手回一句（如 确实/哈哈这真的离谱/绷不住）"),
    ("短", "15~40 个字，一两句话接住对方的点"),
    ("中", "40~90 个字，补一点自己的经验或观点"),
]

# AI-typical fillers that give essays away
AIISMS = [
    "总之", "综上", "综上所述", "总而言之", "希望对你有帮助", "希望能帮到你",
    "值得注意的是", "值得一提的是", "不得不说", "总的来说", "首先", "其次",
    "再者", "最后但同样重要", "众所周知", "在这个快节奏的时代", "让我们",
    "作为一名", "作为一个AI", "作为一个机器人", "我无法", "抱歉，我",
]

# markdown structures that look wrong in short comments
MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
MD_HEADER = re.compile(r"^#{1,6}\s+", re.M)
MD_LIST = re.compile(r"^\s*[-*]\s+", re.M)
MD_HR = re.compile(r"^\s*---+\s*$", re.M)

CASUAL_TAILS = ["哈哈", "确实", "好家伙", "绷", "笑死", "有点东西", "蚌"]

SENT_END = re.compile(r"([。！？!?…]|\.)")


def _sentence_cut(text, limit):
    """Trim at a sentence boundary under limit."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.end() for m in SENT_END.finditer(cut)]
    if ends:
        return cut[: ends[-1]].rstrip()
    return cut.rstrip() + "…"


def strip_aiisms(text):
    for phrase in AIISMS:
        text = text.replace(phrase, "")
    return text


def flatten_markdown(text):
    """Comments should not look like documents."""
    text = MD_BOLD.sub(r"\1", text)
    text = MD_HEADER.sub("", text)
    text = MD_LIST.sub("", text)
    text = MD_HR.sub("", text)
    text = text.replace("```", "")
    return text


def vary_emoji(text, kind="comment"):
    """Keep at most one emoticon; strip trailing emoji piles."""
    return re.sub(r"(\s*[😀😃😄😁😆😅🤣😂🙂😉😊😍🤔😎😭😱😳😁]{2,})",
                  lambda m: m.group(1).strip()[:2], text)


class StyleSkill:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.comment_max = int(cfg.get("style_comment_max", COMMENT_MAX))
        self.post_max = int(cfg.get("style_post_max", POST_MAX))

    def humanize(self, text, kind="comment"):
        """Post-process LLM output into a human-sounding shape."""
        if not text:
            return text
        t = strip_aiisms(text.strip())
        if kind == "comment":
            t = flatten_markdown(t)
            t = vary_emoji(t)
            t = re.sub(r"\n{2,}", "\n", t)          # single line feels casual
            t = _sentence_cut(t, self.comment_max)
        elif kind == "post":
            t = _sentence_cut(t, self.post_max)
        t = re.sub(r"[ \t]+\n", "\n", t)
        return t.strip()

    def enforce_length(self, text, kind="comment", agent=None):
        """Only guard against essay-length output; the model owns its length."""
        limit = self.comment_max if kind == "comment" else self.post_max
        if len(text) <= limit:
            return self.humanize(text, kind)
        # one shorten round only when way over the generous cap
        if agent is not None and getattr(agent, "llm", None):
            try:
                shorter = agent.llm.text(
                    "把下面的论坛发言压缩到 %d 字以内，保留原语气，只输出压缩后的正文：\n%s"
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
        return random.choice(LENGTH_DICE)

    def length_hint(self, kind="comment"):
        if kind == "comment":
            return ("长度自己看着定：真人回帖经常就 3~15 个字，偶尔才写长；"
                    "超过 120 字基本必是真人不写的；")
        return "长度 %d~%d 字；" % (COMMENT_TARGET, self.post_max)

    def tone_hint(self):
        return (
            "语气：像论坛老哥随手打字——短句、口语、可以带梗（如 绷/好家伙/确实），"
            "句子允许不完整；不要排比、不要分点、不要总结句、不要客套开场白；"
            "颜文字最多 1 个且别每次都带；绝不出现 AI 说明文结构。"
        )

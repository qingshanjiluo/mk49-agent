"""Markdown 渲染/美化层：把 LLM 原始输出整理成论坛 Vditor 能漂亮渲染的正文。

职责：
- normalize()      : 标准化空白/标题/引用/分割线，避免挤成一坨
- auto_code()      : 识别命令、配置、数据、日志类内容 -> 自动包成 ```代码块``` 高亮
- cards()          : 站内卡片注入（帖子/人物），总数强制 <= 10（论坛硬限制）
- pretty_comment() : 引用父楼 + 正文 + 可选代码块/卡片，组成标准楼中楼评论
- pretty_post()    : 小标题 + 正文 + 配图 + 卡片 + 分隔线，组成标准帖子
"""

import re

from .content import quote_block, truncate, thread_card, user_card

MAX_CARDS = 10
CARD_RE = re.compile(r"\[(?:threadcard|usercard):[1-9]\d*\]")
IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")

# 内容看起来像"命令/配置/数据"的信号
CMD_LINE = re.compile(
    r"^\s{0,3}(\$\s+\S|GET\s+/|POST\s+/|pip\s+install|python\s+\S|\w+==[\w.]+"
    r"|[A-Za-z_][\w.]*\s*[=:]\s*\S|#{1,6}\s+\S|\d{1,3}(\.\d+){1,3}\b)"
)
LOG_LINE = re.compile(r"^\s*(INFO|WARN|ERROR|DEBUG|TRACE|\[\d{2}:\d{2}:\d{2}\])")


def count_cards(text):
    return len(CARD_RE.findall(text or ""))


def inject_cards(text, cards):
    """把额外卡片追加到正文，整体不超过论坛 10 张限制。"""
    cards = [c for c in cards if c]
    if not cards:
        return text or ""
    room = MAX_CARDS - count_cards(text)
    add = cards[: max(room, 0)]
    if not add:
        return text
    return (text or "").rstrip() + "\n\n" + " ".join(add)


def normalize(text):
    """统一 markdown 空白：块级元素前后留空行，去尾随空格。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.rstrip() for ln in text.split("\n")]
    out = []
    for i, ln in enumerate(lines):
        is_block = bool(
            re.match(r"^(#{1,6}\s|>\s|-{3,}$|```|\d+\.\s|- )", ln)
        )
        prev = lines[i - 1] if i else ""
        prev_block = bool(re.match(r"^(#{1,6}\s|>\s|-{3,}$|```|\d+\.\s|- )", prev))
        if is_block and out and out[-1].strip() and not prev_block and not ln.startswith("> "):
            out.append("")
        elif (prev_block or prev.startswith("> ")) and ln.strip() and not is_block \
                and not ln.startswith("> "):
            out.append("")
        out.append(ln)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def looks_like_block(lines):
    """一组行是否应包进代码块（命令/配置/日志/数据特征 >= 一半）。"""
    if not lines:
        return False
    hits = sum(1 for ln in lines
               if CMD_LINE.match(ln) or LOG_LINE.match(ln) or "|" in ln)
    return hits >= max(2, len(lines) // 2)


def auto_code(text, min_lines=2):
    """把连续的命令/配置/日志行自动包成 ``` 代码块（已包的不动）。"""
    if not text or "```" in text:
        return text
    lines = text.split("\n")
    out, buf = [], []

    def flush():
        if len(buf) >= min_lines and looks_like_block(buf):
            out.append("```")
            out.extend(buf)
            out.append("```")
        else:
            out.extend(buf)
        buf.clear()

    for ln in lines:
        if CMD_LINE.match(ln) or LOG_LINE.match(ln):
            buf.append(ln)
        else:
            flush()
            out.append(ln)
    flush()
    return "\n".join(out)


def auto_link(text):
    """裸链接包成 [域名/路径](url)，避免刷屏式长 URL。"""
    if not text:
        return text

    def rep(m):
        url = m.group(0)
        if "](" in text[max(0, m.start() - 2):m.end() + 1]:
            return url
        label = url.split("//", 1)[-1]
        if len(label) > 40:
            label = label[:37] + "..."
        return "[%s](%s)" % (label, url)

    return re.sub(r"https?://[^\s<>\")\]]+", rep, text)


def beautify(text):
    """一键美化：normalize -> auto_code -> auto_link。"""
    return normalize(auto_link(auto_code(normalize(text))))


def pretty_comment(body, parent_text="", cards=None, with_quote=True):
    """组一条标准评论/楼中楼：引用 + 美化正文 + 卡片。"""
    body = beautify((body or "").strip())
    parts = []
    if with_quote and parent_text:
        q = truncate(parent_text.replace("\n", " ").strip(), 60)
        if q:
            parts.append(quote_block(q))
    parts.append(body)
    text = "\n\n".join(p for p in parts if p)
    return inject_cards(text, cards or [])


def pretty_post(title="", body="", image_url="", image_alt="",
                cards=None, footer=""):
    """组一条标准帖子：标题(如给) + 美化正文 + 配图 + 卡片 + 页脚。"""
    parts = []
    if title and not re.match(r"^#", title or ""):
        parts.append("## %s" % title)
    parts.append(beautify(body or ""))
    if image_url:
        alt = (image_alt or "配图").replace("[", "").replace("]", "")[:30]
        parts.append("![%s](%s)" % (alt, image_url))
    text = "\n\n".join(p for p in parts if p and p.strip())
    text = inject_cards(text, cards or [])
    if footer:
        text = text.rstrip() + "\n\n---\n*" + footer.strip() + "*"
    return text


def shorten_comment_md(text, limit=4000):
    """论坛帖子有 4000 字上限，截断时保证代码块闭合。"""
    if not text or len(text) <= limit:
        return text
    cut = text[:limit]
    if cut.count("```") % 2:
        cut = cut.rsplit("```", 1)[0]
    return cut.rstrip() + "\n\n…(内容过长已截断)"

"""表情包点缀：从论坛自定义 emoji 列表挑一个 :shortcode: 贴到文案尾部。"""

import random
import re

from . import Feature, register

SHORTCODE_RE = re.compile(r":[a-z0-9_]{1,30}:")


@register
class EmojiEnhancer(Feature):
    name = "emoji_enhancer"
    desc = "自动在发言尾部点缀论坛自定义表情（:shortcode:）"
    plan_keys = ()   # 出站文本增强器

    def enhance(self, text, agent, chance=0.55):
        if not text or SHORTCODE_RE.search(text):
            return text
        if random.random() > chance:
            return text
        pool = agent.state.data.get("emoji_pool")
        if not pool:
            try:
                pool = [e.get("shortcode") for e in agent.client.emojis()
                        if e.get("enabled") and e.get("shortcode")]
            except Exception:
                pool = []
            if pool:
                agent.state.data["emoji_pool"] = pool
        if not pool:
            return text
        return "%s :%s:" % (text.rstrip(), random.choice(pool))

    def triggered_by(self, plan, agent):
        return False

    def run(self, agent, plan):
        return 0

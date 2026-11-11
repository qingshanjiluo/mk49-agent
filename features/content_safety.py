"""发布前内容体检：任何出站文本先过规则+LLM 双重检查，风险则改写或拒绝。"""

from mbbs.content import strip_html

from . import Feature, register

FORBIDDEN_PATTERNS = [
    ("政治人物", "习近平|李强|李克强|胡锦涛|温家宝|毛泽东|邓小平|普京|拜登|特朗普"),
    ("敏感事件", "六四|天安门事件|文革|大跃进"),
    ("低俗", "裸聊|约炮|援交|肉便器"),
    ("广告导流", "加微信|加qq|私聊购买|代理招募|telegram群|电报群"),
    ("开盒", "身份证号|家庭住址是|手机号是1[3-9]\\d{9}"),
]

import re


@register
class ContentSafety(Feature):
    name = "content_safety"
    desc = "发布前内容体检：敏感词正则 + LLM 复核，风险文本改写"
    plan_keys = ()

    def triggered_by(self, plan, agent):
        return True  # 守门员，每次 act 都先跑

    def check(self, text, agent):
        """返回 (safe, reason, rewritten_or_none)。"""
        plain = strip_html(text) if "<" in text[:64] else text
        hits = []
        for label, pattern in FORBIDDEN_PATTERNS:
            m = re.search(pattern, plain, re.I)
            if m:
                hits.append("%s:%s" % (label, m.group(0)))
        if hits:
            return False, ";".join(hits), None
        # LLM 复核（可失败，失败视为通过）
        try:
            verdict = agent.llm.json(
                "审核以下论坛发言是否风险（政治/色情/暴力/广告/隐私泄露/人身攻击）。"
                '{"safe":true/false,"reason":"10字内"}\n发言：' + plain[:400],
                system="你是内容安全审核员，只输出JSON。",
                temperature=0.1, max_tokens=120, json_mode=True,
            )
            if verdict.get("safe") is False:
                return False, str(verdict.get("reason", "llm"))[:40], None
        except Exception:
            pass
        return True, "", None

    def run(self, agent, plan):
        return 0  # 由各出站 feature 主动调用 self.check()

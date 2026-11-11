"""热点话题追踪：跨轮统计标题关键词热度，写入状态供速览/报告使用。"""

from collections import Counter, defaultdict

from mbbs.content import truncate

from . import Feature, register
from .daily_digest import _keywords


@register
class HotTopicTracker(Feature):
    name = "hot_topic_tracker"
    desc = "跨轮热点关键词热度榜（供速览引用与 /status 查看）"
    plan_keys = ()

    def triggered_by(self, plan, agent):
        return bool(agent.obs.new_threads) or bool(agent.obs.hot_titles)

    def run(self, agent, plan):
        heat = agent.state.data.setdefault("topic_heat", {})
        changed = 0
        for t in agent.obs.new_threads[:10]:
            title = truncate(t.get("title", ""), 60)
            for w in _keywords(title):
                heat[w] = heat.get(w, 0) + 1
                changed += 1
        # 只留最热的 200 个，防止状态膨胀
        if len(heat) > 200:
            top = dict(Counter(heat).most_common(200))
            agent.state.data["topic_heat"] = top
        if changed:
            agent.state.log("topic_heat", "bumped %d" % changed)
        return 1 if changed else 0

    @staticmethod
    def top(agent, n=8):
        heat = agent.state.data.get("topic_heat") or {}
        return Counter(heat).most_common(n)

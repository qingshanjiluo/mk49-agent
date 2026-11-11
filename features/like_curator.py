"""点赞策展：给质量不错的新帖/评论点赞（每日限额，防刷屏）。"""

import random

from mbbs.content import strip_html, truncate

from . import Feature, register


@register
class LikeCurator(Feature):
    name = "like_curator"
    desc = "按质量信号点赞优质帖子与评论（每日限额）"
    plan_keys = ("like",)

    MAX_PER_DAY = 15

    def triggered_by(self, plan, agent):
        return bool(plan.get("like"))

    def run(self, agent, plan):
        if agent.state.daily_count("likes") >= self.MAX_PER_DAY:
            return 0
        done = 0
        for t in agent.obs.new_threads[:6]:
            if done >= 3:
                break
            if str(t["id"]) in agent.state.data["liked_threads"]:
                continue
            score = self._score(t, agent)
            if score <= 0:
                continue
            try:
                agent.client.like_thread(t["id"], True)
            except Exception as exc:
                agent.log("like thread failed: %s" % exc)
                continue
            agent.state.data["liked_threads"].append(str(t["id"]))
            agent.state.bump_daily("likes")
            agent.state.stat_bump("likes")
            agent.state.log("like", "thread=%s score=%.2f" % (t["id"], score))
            done += 1

        # 顺手给优质评论点赞
        if done and random.random() < 0.5:
            for tid, cs in list(agent.obs.thread_comments.items())[:3]:
                for c in cs[:3]:
                    if (c.get("user") or {}).get("id") == agent.client.user_id:
                        continue
                    if len(strip_html(c.get("content") or "")) < 15:
                        continue
                    try:
                        agent.client.like_post(c["id"], True)
                        agent.state.bump_daily("likes")
                        agent.state.stat_bump("likes")
                        done += 1
                    except Exception:
                        pass
                    break
        return done

    @staticmethod
    def _score(t, agent):
        """简单质量启发式：内容长度 + 已有互动。"""
        content = t.get("_detail") or strip_html(t.get("content_for_indexes") or "")
        length = len(content)
        comments = len(agent.obs.thread_comments.get(t["id"], []))
        if t.get("is_pinned") or t.get("user", {}).get("id") == agent.client.user_id:
            return 0
        score = min(length / 400.0, 1.0) * 0.6 + min(comments / 5.0, 1.0) * 0.4
        return score if score >= 0.35 else 0

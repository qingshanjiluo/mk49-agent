"""投票参与：扫描新帖里的开放投票，按偏好（或 LLM）投票并回帖说明。"""

from . import Feature, register


@register
class PollRider(Feature):
    name = "poll_rider"
    desc = "自动发现开放投票并参与（thread.votePoll 权限）"
    plan_keys = ("vote",)

    # Never auto-vote on governance/election style polls.
    AVOID_KEYWORDS = ["选举", "民选", "竞选", "投票用贴", "参选", "管理员"]

    # Never auto-vote on governance/election style polls.
    AVOID_KEYWORDS = ["选举", "民选", "竞选", "投票用贴", "参选", "管理员"]

    def triggered_by(self, plan, agent):
        return bool(plan.get("vote"))

    def run(self, agent, plan):
        done = 0
        avoid = agent.cfg.get("avoid_poll_keywords") or self.AVOID_KEYWORDS
        for t in agent.obs.new_threads[:6]:
            title = (t.get("title") or "")
            if any(k in title for k in avoid):
                continue  # never auto-vote in elections/moderation polls
            try:
                polls = agent.client.polls_of_thread(t["id"])
            except Exception:
                continue
            for poll in polls:
                if poll.get("is_closed") or not poll.get("can_vote"):
                    continue
                if poll.get("selected_option_ids"):
                    continue
                opt = self._choose(agent, poll)
                if not opt:
                    continue
                try:
                    # API requires singular option_id (list for multi-choice)
                    value = opt if poll.get("allow_multiple") and len(opt) > 1 else opt[0]
                    agent.client.vote_poll(poll["poll_id"], value)
                except Exception as exc:
                    agent.log("vote failed: %s" % exc)
                    continue
                agent.state.bump_daily("poll_votes")
                agent.state.stat_bump("poll_votes")
                agent.state.log("vote", "thread=%s poll=%s opt=%s"
                                % (t["id"], poll["poll_id"], opt))
                agent.log("voted poll %s option %s" % (poll["poll_id"], opt))
                done += 1
        return done

    @staticmethod
    def _choose(agent, poll):
        options = poll.get("options") or []
        if not options:
            return None
        if poll.get("allow_multiple"):
            return [options[0]["id"]]
        # 尝试 LLM 选一个，失败则随机（保持轻量）
        labels = [o.get("text", "") for o in options]
        try:
            idx = agent.llm.json(
                "为投票选一项，输出 {\"pick\":序号}，序号从0开始。"
                "选项：" + str(labels),
                system="只输出JSON", temperature=0.3, max_tokens=60, json_mode=True,
            ).get("pick")
            if isinstance(idx, int) and 0 <= idx < len(options):
                return [options[idx]["id"]]
        except Exception:
            pass
        import random
        return [random.choice(options)["id"]]

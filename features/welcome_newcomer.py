"""新人欢迎：检测首次发帖的用户，在帖子里友好迎接（带人物卡片）。"""

from mbbs.content import strip_html, truncate, user_card

from . import Feature, register

NEWBIE_CATEGORIES = {24, 32}  # 未认证用户区 / 新人必读


@register
class WelcomeNewcomer(Feature):
    name = "welcome_newcomer"
    desc = "发现新人首帖后自动欢迎（含 usercard 引导）"
    plan_keys = ("welcome",)

    def triggered_by(self, plan, agent):
        if not agent.cfg.get("welcome_newcomers", True):
            return False
        return bool(plan.get("welcome")) or bool(agent.obs.new_threads)

    def run(self, agent, plan):
        done = 0
        for t in agent.obs.new_threads[:6]:
            uid = (t.get("user") or {}).get("id")
            if not uid or uid == agent.client.user_id:
                continue
            if str(uid) in agent.state.data["welcomed_users"]:
                continue
            if not self._looks_new(agent, t, uid):
                continue
            if not self._welcome(agent, t, uid):
                continue
            agent.state.data["welcomed_users"].append(str(uid))
            done += 1
        return done

    def _looks_new(self, agent, thread, uid):
        """Newcomer = small thread_count / young account / newbie category."""
        if thread.get("category_id") in NEWBIE_CATEGORIES:
            return True
        try:
            info = agent.client.get_user(uid) or {}
        except Exception:
            return False
        if (info.get("thread_count") or 99) <= 2:
            return True
        joined = str(info.get("joined_at") or "")
        if joined:
            try:
                from datetime import datetime, timezone
                age_days = (datetime.now(timezone.utc)
                            - datetime.fromisoformat(joined.replace("Z", "+00:00"))).days
                return age_days <= 7
            except Exception:
                return False
        return False

    def _welcome(self, agent, thread, uid):
        try:
            info = agent.client.get_user(uid) or {}
        except Exception:
            info = {}
        nick = truncate((info.get("nickname") or thread.get("user", {}).get("nickname")
                         or "新朋友"), 16)
        try:
            text = agent.llm.text(
                "论坛来了位新用户「%s」，他刚发了帖子《%s》。"
                "写一句 40~80 字的友好欢迎语，自然不客套，可带1个颜文字，"
                "结尾自然带上人物卡片语法 %s（原样保留该语法）。"
                "只输出欢迎语。"
                % (nick, truncate(thread.get("title", ""), 30), user_card(uid)),
                system="你是热心论坛老用户。", max_tokens=200,
            )
        except Exception as exc:
            agent.log("welcome llm failed: %s" % exc)
            text = "欢迎 %s，帖子里慢慢逛~ %s" % (nick, user_card(uid))
        text = (text or "").strip()
        if user_card(uid) not in text:
            text = "%s\n\n%s" % (text, user_card(uid))
        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(text, agent)
            if not ok:
                agent.log("welcome blocked: %s" % reason)
                return False
        data = None
        try:
            data = agent.client.create_post(thread["id"], text)
        except Exception as exc:
            agent.log("welcome post failed: %s" % exc)
            return False
        if data and data.get("id"):
            agent.state.bump_daily("comments")
            agent.state.stat_bump("welcome")
            agent.state.log("welcome", "uid=%s thread=%s" % (uid, thread["id"]))
            agent.log("welcomed %s in thread %s" % (nick, thread["id"]))
            return True
        return False

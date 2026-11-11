"""配图发帖：LLM 定主题 -> 生成图片 -> 上传论坛存储 -> markdown 内联发帖。"""

from mk49 import images as img

from . import Feature, register


DEFAULT_CATEGORIES = [2]  # 聊天区


@register
class ImagePost(Feature):
    name = "image_post"
    desc = "生图+上传+URL内联的全自动配图发帖"
    plan_keys = ("image_thread",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("image_thread")) and agent.cfg.get("enable_image_posts", True)

    def run(self, agent, plan):
        if agent.state.daily_count("threads") >= agent.cfg["daily_post_limit"]:
            return 0
        topic = plan.get("thread_topic") or ""
        if not topic:
            topic = self._pick_topic(agent)
        if not topic:
            return 0

        try:
            prompt = agent.llm.image_prompt_for(topic)
        except Exception as exc:
            agent.log("image prompt failed: %s" % exc)
            prompt = topic

        try:
            raw, ext = img.generate(prompt, provider=agent.cfg.get("image_provider"))
            raw, ext = img.fit_for_forum(raw)
            url = img.upload_to_forum(agent.client, raw,
                                      "agent_%d.%s" % (int(_now()), ext))
            agent.state.stat_bump("images")
        except Exception as exc:
            agent.log("image gen/upload failed: %s" % exc)
            url = ""

        try:
            title = agent.llm.new_thread_title(self._cat_name(agent), [topic])
        except Exception:
            title = ""
        title = (title or "").strip()[:40]
        if not title:
            title = (topic or "随手一发").replace("用户要求", "").strip()[:30]

        try:
            body = agent.llm.new_thread_body(title, topic)
        except Exception:
            body = topic

        from mbbs.render import pretty_post
        body = pretty_post(
            title="",
            body=body,
            image_url=url,
            image_alt=(topic or "配图")[:24],
            footer="由幻想智能体生成配图",
        )

        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(title + "\n" + body, agent)
            if not ok:
                agent.log("image thread blocked by safety: %s" % reason)
                return 0

        cat = plan.get("thread_category") or DEFAULT_CATEGORIES[0]
        data = agent.client.create_thread(cat, title, body)
        if data and data.get("id"):
            agent.state.bump_daily("threads")
            agent.state.stat_bump("threads")
            agent.state.log("image_post", "thread=%s url=%s" % (data["id"], url))
            agent.log("image thread created: %s (%s)" % (title, data["id"]))
            return 1
        return 0

    def _pick_topic(self, agent):
        titles = agent.obs.hot_titles or ["日常闲聊"]
        try:
            return agent.llm.text(
                "论坛最近帖子：" + " / ".join(titles[:8]) +
                "\n从中提炼一个适合发帖配图的新话题（一句中文，15字内），只输出话题。",
                max_tokens=60,
            ).strip()
        except Exception:
            return titles[0] if titles else ""

    @staticmethod
    def _cat_name(agent):
        return "聊天"


def _now():
    import time
    return time.time()


def _md_img(url, alt):
    alt = (alt or "").replace("[", "").replace("]", "")[:30]
    return "![%s](%s)" % (alt, url)

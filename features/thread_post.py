"""Generic thread creator: the consumer for plan.create_thread (slots or LLM).

Handles quota, topic/title/body generation, optional image, safety gate,
pretty_post rendering, dedupe of repeated titles. Replaces the old
image_post trigger path (image_post is disabled and merged here).
"""

import re
import time

from . import Feature, register


@register
class ThreadPost(Feature):
    name = "thread_post"
    desc = ("Create a thread (text, optionally with a generated image). "
            "Consumes plan.create_thread from posting slots or LLM plan.")
    plan_keys = ("create_thread",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("create_thread") or plan.get("image_thread"))

    def run(self, agent, plan):
        if agent.state.daily_count("threads") >= agent.cfg["daily_post_limit"]:
            agent.log("thread_post: daily quota reached, skip")
            return 0

        topic = (plan.get("thread_topic") or "").strip()
        category = (plan.get("thread_category")
                    or (agent.cfg.get("community_categories") or [2])[0])
        history = [t for t in agent.obs.hot_titles[:10]]

        if not topic:
            try:
                topic = agent.llm.text(
                    "Forum hot topics: " + " / ".join(history[:8]) +
                    "\nPick ONE fresh topic for a new thread in category %s "
                    "(one Chinese sentence <=18 chars, concrete, not a repeat). "
                    "Output only the topic." % category,
                    tier="fast", max_tokens=60, temperature=0.8).strip()
            except Exception as exc:
                agent.log("thread_post topic fail: %s" % exc)
            if not topic:
                return 0

        try:
            title = agent.llm.new_thread_title(self._cat_name(agent, category),
                                               [topic], history=history)
        except Exception as exc:
            agent.log("thread_post title fail: %s" % exc)
            title = ""
        title = (title or "").strip()[:36] or (topic[:30] or "随手一发")
        # dedupe: never repost a title that already ran today
        for e in (agent.memory.state.data.get("thread_memory") or {}).values():
            for ent in e:
                if ent.get("kind") == "mine" and title[:12] in (ent.get("text") or ""):
                    agent.log("thread_post: title seen before, skip")
                    return 0

        try:
            body = agent.llm.new_thread_body(title, topic)
        except Exception as exc:
            agent.log("thread_post body fail: %s" % exc)
            body = topic

        image_url = ""
        want_image = bool(plan.get("image_thread")
                          or plan.get("posting_slot")
                          or agent.cfg.get("enable_image_posts"))
        if want_image:
            image_url = self._gen_image(agent, topic, title)

        from mbbs.render import pretty_post
        body = pretty_post(body=body, image_url=image_url,
                           image_alt=(topic or "")[:20],
                           footer="由幻想智能体发布")

        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(title + "\n" + body, agent)
            if not ok:
                agent.log("thread_post blocked: %s" % reason)
                agent.state.log("safety_block", reason)
                return 0

        data = self._create_with_retry(agent, category, title, body)
        if not data or not data.get("id"):
            return 0

        agent.state.bump_daily("threads")
        agent.state.stat_bump("threads")
        agent.memory.record_reply(data["id"], data["id"], body)
        slot = plan.get("posting_slot")
        if slot:
            used = agent.state._day_bucket().setdefault("slots", {})
            used[slot] = True
            agent.state.log("slot", slot)
        agent.state.log("thread_post", "thread=%s cat=%s img=%s"
                        % (data["id"], category, bool(image_url)))
        agent.log("thread created: %s (%s)" % (title, data["id"]))
        return 1

    # -------------------------------------------------
    @staticmethod
    def _create_with_retry(agent, category, title, body):
        """Retry once after rate-limit style errors."""
        for attempt in range(2):
            try:
                return agent.client.create_thread(category, title, body)
            except Exception as exc:
                msg = str(exc)
                wait = None
                m = re.search(r"(\d+)\s*秒", msg)
                if m:
                    wait = int(m.group(1))
                if attempt == 0 and (wait or "频率" in msg or "频繁" in msg):
                    nap = (wait or 60) + 5
                    agent.log("thread_post rate limited, sleep %ss" % nap)
                    time.sleep(min(nap, 300))
                    continue
                agent.log("thread_post create failed: %s" % msg[:120])
                agent.state.log("thread_post_error", msg[:160])
                return None
        return None

    @staticmethod
    def _gen_image(agent, topic, title):
        try:
            from mk49 import images as img
            prompt = agent.llm.image_prompt_for(topic, title)
            raw, ext = img.generate(prompt, timeout=120)
            raw, ext = img.fit_for_forum(raw)
            url = img.upload_to_forum(agent.client, raw,
                                      "agent_%d.%s" % (int(time.time()), ext))
            agent.state.stat_bump("images")
            return url
        except Exception as exc:
            agent.log("thread_post image skipped: %s" % str(exc)[:100])
            return ""

    @staticmethod
    def _cat_name(agent, category):
        names = agent.obs.category_names or {}
        try:
            return names.get(category) or ""
        except Exception:
            return ""

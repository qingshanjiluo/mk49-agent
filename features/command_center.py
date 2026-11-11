"""命令中心：在机器人自己的帖子/楼层里下指令，agent 执行并回执。

支持：
  /help            帮助
  /summary [id]    长帖摘要
  /image <描述>    生图并回帖内联
  /card <tid>      插入帖子卡片
  /post <板块> <主题>  立刻发帖
  /digest          立即发布速览
  /status          运行状态
  自然语言问题会交给 LLM 回答
"""

import re

from mbbs.content import strip_html, thread_card, truncate

from . import Feature, register

CMD_RE = re.compile(r"^\s*/([a-zA-Z]+)\s*(.*)$", re.S)


@register
class CommandCenter(Feature):
    name = "command_center"
    desc = "在自己的帖子/评论下发 /命令 驱动 agent 执行动作"
    plan_keys = ()   # 每轮主动扫描自己帖子的新评论

    def triggered_by(self, plan, agent):
        return bool(agent.obs.bot_threads)

    def run(self, agent, plan):
        done = 0
        for item in agent.obs.bot_threads:
            thread = item["thread"]
            for c in item["comments"]:
                if (c.get("user") or {}).get("id") == agent.client.user_id:
                    continue
                plain = strip_html(c.get("content") or "").strip()
                m = CMD_RE.match(plain)
                if not m:
                    # 自然语言 @ 机器人 也交给 LLM 应答
                    if not self._should_chat(agent, plain):
                        continue
                    reply = self._chat(agent, thread, plain)
                else:
                    reply = self._dispatch(agent, m.group(1).lower(), m.group(2).strip(), thread)
                if not reply:
                    continue
                safety = agent.features.get("content_safety")
                if safety:
                    ok, reason, _ = safety.check(reply, agent)
                    if not ok:
                        reply = "指令已收到，但内容未通过安全检查（%s）。" % reason
                try:
                    data = agent.client.reply_comment(c["id"], reply[:3500])
                except Exception as exc:
                    agent.log("command reply failed: %s" % exc)
                    continue
                if data and data.get("id"):
                    agent.state.bump_daily("comments")
                    agent.state.log("command", "%s -> post=%s"
                                    % (m.group(1) if m else "chat", data["id"]))
                    done += 1
        return done

    # ------------------------------------------------ pieces
    def _should_chat(self, agent, plain):
        if "@" + agent.username in plain:
            return True
        if agent.nickname and agent.nickname in plain:
            return True
        return plain.endswith("?") and any(k in plain for k in ("你", "助手", "机器人"))

    def _chat(self, agent, thread, question):
        try:
            return agent.llm.text(
                "帖子《%s》下有人问：%s\n请以论坛助手身份自然回答（100字内）。"
                % (truncate(thread.get("title", ""), 30), question[:300]),
                system="简洁友好", max_tokens=300,
            )
        except Exception as exc:
            agent.log("chat failed: %s" % exc)
            return "抱歉，我这边脑子暂时卡住了，稍后再试喵~"

    def _dispatch(self, agent, cmd, arg, thread):
        if cmd == "help":
            return ("/help 帮助\n"
                    "/summary — 摘要当前帖\n"
                    "/image <描述> — 生图并回帖\n"
                    "/card <帖子id> — 插入帖子卡片\n"
                    "/post <板块id> <主题> — 立即发帖\n"
                    "/digest — 立即发布每日速览\n"
                    "/status — 运行状态")
        if cmd == "summary":
            return _summarize(agent, thread, arg)
        if cmd == "image":
            return _make_image(agent, arg or "a cute cat")
        if cmd == "card":
            tid = arg.strip()
            return thread_card(tid) if tid.isdigit() else "用法：/card 48248"
        if cmd == "post":
            parts = arg.split(None, 1)
            if not parts:
                return "用法：/post 2 话题描述"
            cat = parts[0] if parts[0].isdigit() else "2"
            topic = parts[1] if len(parts) > 1 else ""
            return _create_post(agent, int(cat), topic)
        if cmd == "digest":
            feat = agent.features.get("daily_digest")
            n = feat.run(agent, {"daily_digest": True}) if feat else 0
            return "速览已发布。" if n else "速览今日已发布过或暂无内容。"
        if cmd == "status":
            s = agent.state.data.get("stats", {})
            return ("状态：已跑 %s 轮 / 发帖 %s / 回帖 %s / 点赞 %s / 生图 %s"
                    % (s.get("cycles", 0), s.get("threads", 0), s.get("comments", 0),
                       s.get("likes", 0), s.get("images", 0)))
        return "未知命令 /%s，发送 /help 查看帮助。" % cmd


def _summarize(agent, thread, arg):
    try:
        detail = thread.get("_detail") or strip_html(thread.get("content_for_indexes") or "")
        text = agent.llm.text(
            "用3行以内总结这个帖子的要点，输出纯文本：\n《%s》\n%s"
            % (truncate(thread.get("title", ""), 40), detail[:1500]),
            max_tokens=300,
        )
        return "📌 摘要：\n" + (text or "").strip()
    except Exception as exc:
        return "摘要失败：%s" % exc


def _make_image(agent, desc):
    from mk49 import images as img
    try:
        raw, ext = img.generate(desc)
        raw, ext = img.fit_for_forum(raw)
        url = img.upload_to_forum(agent.client, raw, "cmd_%d.%s" % (int(_now()), ext))
        agent.state.stat_bump("images")
        return "🖼️ %s\n\n![img](%s)" % (desc[:40], url)
    except Exception as exc:
        return "生图失败：%s" % exc


def _create_post(agent, category_id, topic):
    if agent.state.daily_count("threads") >= agent.cfg["daily_post_limit"]:
        return "今日发帖额度已用完。"
    try:
        title = agent.llm.new_thread_title(str(category_id), [topic])[:40]
        body = agent.llm.new_thread_body(title, topic)
    except Exception as exc:
        return "生成失败：%s" % exc
    try:
        data = agent.client.create_thread(category_id, title, body)
    except Exception as exc:
        return "发帖失败：%s" % exc
    if data and data.get("id"):
        agent.state.bump_daily("threads")
        agent.state.stat_bump("threads")
        return "已发布：%s (%s)" % (title, data["id"])
    return "发帖失败。"


def _now():
    import time
    return time.time()

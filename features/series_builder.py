"""系列合集：把同主题新帖自动收进一个 series（合集/文集）。

论坛支持 series（用户级合集），此功能在发现同主题第 2、3... 帖时自动建合集
并把帖子归入，便于读者连续阅读。
"""

from mbbs.content import truncate

from . import Feature, register

MIN_FOR_SERIES = 2


@register
class SeriesBuilder(Feature):
    name = "series_builder"
    desc = "同主题帖子自动归入系列合集（series）"
    plan_keys = ("create_thread", "reply_comment_ids")

    def triggered_by(self, plan, agent):
        return bool(agent.obs.new_threads)

    def run(self, agent, plan):
        # 用 LLM 把新帖分组到一个粗主题
        titles = [(t["id"], truncate(t.get("title", ""), 30))
                  for t in agent.obs.new_threads[:8]]
        if len(titles) < MIN_FOR_SERIES:
            return 0
        try:
            grouping = agent.llm.json(
                "把下面帖子按主题聚成最多2组，输出 "
                '{"groups":[{"name":"6字内主题名","ids":[帖子id]}]}\n'
                + str(titles),
                system="只输出JSON", temperature=0.2, max_tokens=300, json_mode=True,
            )
        except Exception as exc:
            agent.log("series grouping failed: %s" % exc)
            return 0
        done = 0
        series_map = agent.state.data.setdefault("series_map", {})  # name -> series_id
        for g in (grouping.get("groups") or [])[:2]:
            name = truncate(str(g.get("name", "")), 12)
            ids = [int(i) for i in (g.get("ids") or []) if str(i).isdigit()]
            if not name or len(ids) < MIN_FOR_SERIES:
                continue
            sid = series_map.get(name)
            if not sid:
                try:
                    created = agent.client.create_series("助手精选·" + name,
                                                          "自动聚合的相关帖子")
                    sid = (created or {}).get("id")
                except Exception as exc:
                    agent.log("create series failed: %s" % exc)
                    continue
                if not sid:
                    continue
                series_map[name] = sid
            for tid in ids:
                if str(tid) in agent.state.data.get("series_assigned", []):
                    continue
                try:
                    agent.client.modify_thread(tid, series_id=sid)
                except Exception as exc:
                    agent.log("assign series failed: %s" % exc)
                    continue
                agent.state.data.setdefault("series_assigned", []).append(str(tid))
                agent.state.log("series", "%s <- %s" % (name, tid))
                agent.log("thread %s -> series %s" % (tid, name))
                done += 1
        return done

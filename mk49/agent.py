"""Autonomous agent core: observe -> decide -> act -> reflect.

The decision engine first asks the LLM for a JSON action plan; if the LLM is
unavailable or returns garbage it falls back to a deterministic weighted
policy driven by quotas in State. Either way the agent keeps moving.
"""

import json
import random
import time
import traceback
from datetime import date, datetime

from mbbs.content import strip_html, truncate
from .context import is_replyable, render_thread_block, thread_meta, comment_meta

from .llm import extract_json
from .style import StyleSkill
from .memory import InteractionMemory
from .workflow import Workflow
from .tools import build_registry


def _today():
    from datetime import date
    return date.today().isoformat()


class Observation:
    """One snapshot of the forum, rebuilt every cycle."""

    def __init__(self):
        self.new_threads = []       # unseen thread summaries (with detail)
        self.thread_comments = {}   # tid -> [comment dicts]
        self.new_comments = []     # flat unseen comments [(tid, comment)]
        self.bot_threads = []      # own threads with their comments
        self.mention_hits = []     # comments that mention/@ the agent
        self.unread = 0
        self.hot_titles = []
        self.replyable = []        # threads we may answer (filters applied)
        self.skipped = {}           # tid -> reason, audit trail
        self.category_names = {}    # cat id -> name


class Agent:
    def __init__(self, client, llm, state, cfg, features):
        self.client = client
        self.llm = llm
        self.state = state
        self.cfg = cfg
        self.features = features          # {name: Feature instance}
        self.nickname = ""
        self.username = cfg.get("username", "")
        self.obs = Observation()
        self.last_plan = None
        self.style = StyleSkill(cfg)
        self.memory = InteractionMemory(state)
        self.workflow = Workflow(state)
        self.registry = build_registry()

    # ------------------------------------------------ logging
    def log(self, msg):
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg))

    # ------------------------------------------------ lifecycle
    def bootstrap(self):
        if not self.client.ensure_login():
            raise RuntimeError("login failed")
        me = self.client.me() or {}
        self.nickname = me.get("nickname") or self.username
        gid = (me.get("group") or {}).get("id")
        perms = self.client.user_permissions(gid) if gid else []
        self.my_perms = set(perms)
        self.log("login ok: %s (group=%s, perms=%d)"
                 % (self.nickname, (me.get("group") or {}).get("name"), len(perms)))
        # inject learned forum knowledge into every LLM call
        kb_md = (self.cfg.get("knowledge_file") or "state/knowledge.json")
        kb_md = kb_md.rsplit(".", 1)[0] + ".md"
        try:
            with open(kb_md, "r", encoding="utf-8") as fh:
                self.llm.knowledge_text = fh.read()[:2500]
            self.log("knowledge loaded: %d chars" % len(self.llm.knowledge_text))
        except OSError:
            pass

    # ------------------------------------------------ observation
    def observe(self):
        obs = Observation()
        cfg = self.cfg
        my_id = self.client.user_id

        names = {}
        try:
            for c in self.client.categories():
                names[c.get('id')] = c.get('name')
        except Exception:
            names = {}
        obs.category_names = names

        for cat in cfg['target_categories']:
            try:
                threads, _ = self.client.list_threads(
                    category_id=cat, page_limit=cfg['max_threads_per_cycle'])
            except Exception as exc:
                self.log('observe category %s failed: %s' % (cat, exc))
                continue
            for t in threads:
                tid = t.get('id')
                if not tid or self.state.seen_thread(tid):
                    continue
                if t.get('is_draft') or t.get('deleted_at'):
                    continue
                ok, why = is_replyable(t, cfg, my_id)
                t['_replyable'] = ok
                t['_skip_reason'] = why
                t['_own'] = (t.get('user') or {}).get('id') == my_id
                obs.new_threads.append(t)
                obs.hot_titles.append(truncate(t.get('title', ''), 40))
                if ok:
                    obs.replyable.append(t)
                else:
                    obs.skipped[tid] = why

        for t in obs.new_threads[:12]:
            tid = t['id']
            try:
                detail = self.client.thread_detail(tid) or t
                t['_detail'] = strip_html(
                    detail.get('content') or detail.get('content_for_indexes') or '')
                t['_body_html'] = detail.get('content') or ''
            except Exception as exc:
                self.log('detail thread %s failed: %s' % (tid, exc))
                t.setdefault('_detail', '')
            if t.get('disable_post'):
                t['_comments'] = []
                continue
            try:
                comments = self.client.all_comments(tid)
            except Exception as exc:
                self.log('comments thread %s failed: %s' % (tid, exc))
                comments = []
            marked = []
            for idx, c in enumerate(comments):
                c['_own'] = (c.get('user') or {}).get('id') == my_id
                c['_floor'] = idx + 1
                c['_depth'] = 1 if c.get('is_comment') else 0
                marked.append(c)
                if self.state.seen_post(c.get('id')):
                    continue
                obs.new_comments.append((tid, c))
                if self._mentions_me(c):
                    obs.mention_hits.append((tid, c))
            t['_comments'] = marked

        try:
            mine, _ = self.client.list_threads(user_id=my_id, page_limit=8)
        except Exception:
            mine = []
        for t in mine:
            tid = t.get('id')
            if not tid:
                continue
            try:
                comments = self.client.all_comments(tid)
            except Exception:
                comments = []
            obs.bot_threads.append({'thread': t, 'comments': comments})

        try:
            obs.unread = self.client.unread_count()
        except Exception:
            obs.unread = 0

        self.obs = obs
        self.state.stat_bump('cycles')
        return obs

    def _mentions_me(self, comment):
        text = strip_html(comment.get("content") or "")
        nick = self.nickname or ""
        for name in (self.username, nick):
            if name and len(name) >= 2 and name in text:
                return True
        return ("@" + self.username) in text

    # ------------------------------------------------ decision
    def decide(self):
        """Return an action plan dict; falls back to heuristic weights."""
        plan = self._llm_plan()
        if plan is None:
            plan = self._heuristic_plan()
        plan = self._apply_schedules(plan)
        self.last_plan = plan
        self.state.log("plan", json.dumps(plan, ensure_ascii=False)[:300])
        return plan

    # ------------------------------------------------ skills
    def refresh_skills(self):
        """Load skills/*.txt into the LLM system prompt knowledge."""
        import os
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "skills")
        parts = []
        try:
            for fn in sorted(os.listdir(skills_dir)):
                if fn.endswith(".txt"):
                    with open(os.path.join(skills_dir, fn), "r",
                              encoding="utf-8", errors="replace") as fh:
                        body = fh.read().strip()
                    if body:
                        parts.append("[skill:%s]\n%s" % (fn[:-4], body))
        except OSError:
            pass
        base = self.llm.knowledge_text.split("[skill:", 1)[0]
        self.llm.knowledge_text = (base + "\n\n" + "\n\n".join(parts)).strip()

    # ------------------------------------------------ schedules
    def is_quiet_now(self):
        """Night quiet hours: no forum writes (default 23:00-08:00)."""
        from datetime import datetime
        start = int(self.cfg.get("quiet_start", 23))
        end = int(self.cfg.get("quiet_end", 8))
        hour = datetime.now().hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end  # window crosses midnight

    def _slot_due(self):
        """Fixed posting slots (fixed posting data). Returns slot or None."""
        from datetime import datetime
        slots = self.cfg.get("posting_slots") or []
        if not slots:
            return None
        now = datetime.now()
        used = self.state._day_bucket().get("slots", {})
        for slot in slots:
            try:
                hh, mm = [int(x) for x in str(slot).split(":")]
            except (ValueError, AttributeError):
                continue
            due_min = hh * 60 + mm
            now_min = now.hour * 60 + now.minute
            if slot not in used and 0 <= now_min - due_min <= 45:
                return slot
        return None

    def _apply_schedules(self, plan):
        """Time-driven actions independent of the LLM plan."""
        from datetime import datetime
        hour = datetime.now().hour
        if 9 <= hour < 23 and self.state.daily_count("digest") == 0:
            plan["daily_digest"] = True
        else:
            plan.setdefault("daily_digest", False)
        # knowledge pass: once per day, any hour (read-only work)
        plan["learn"] = self.state.daily_count("learn") == 0
        # fixed posting slots: deterministic daily thread schedule
        slot = self._slot_due()
        plan["posting_slot"] = slot
        if slot and self.state.daily_count("threads") < self.cfg["daily_post_limit"]:
            plan["create_thread"] = True
            plan.setdefault("thread_category",
                            (self.cfg["target_categories"] or [2])[0])
            plan.setdefault("image_thread",
                            bool(self.cfg.get("enable_image_posts")))
        return plan

    def _observation_digest(self):
        """Compact but metadata-rich view for the planner."""
        o = self.obs
        my_id = self.client.user_id
        blocks = []
        for t in o.replyable[:6]:
            blocks.append(render_thread_block(
                t, t.get('_comments') or [], self.cfg, my_id,
                o.category_names, t.get('_detail') or '', max_comments=6))

        return {
            "me": {"nickname": truncate(self.nickname, 20), "id": my_id},
            "candidate_threads": blocks,
            "skipped_threads": [
                "%s (%s)" % (tid, why) for tid, why in list(o.skipped.items())[:10]],
            "mentions": [
                {"thread": tid, "from": (c.get("user") or {}).get("nickname"),
                 "text": truncate(strip_html(c.get("content")), 120)}
                for tid, c in o.mention_hits[:5]],
            "unread_messages": o.unread,
            "quota": {
                "threads_used": self.state.daily_count("threads"),
                "threads_limit": self.cfg["daily_post_limit"],
                "comments_used": self.state.daily_count("comments"),
                "comments_limit": self.cfg.get("daily_comment_limit", 8),
            },
        }

    def _llm_plan(self, retries=1):
        """Ask the planner for targets; it never overrides the safety filters."""
        digest = self._observation_digest()
        prompt = (
            "下面是一个论坛 agent 本轮的观察数据（JSON）。\n"
            "请你决定：要回复哪些帖子/楼层、要不要发新帖、要发什么主题。\n"
            "输出 JSON：\n"
            "{\n"
            '  "reply_targets": [{"thread": <帖子id>, "post": <楼层id或0表示整帖>}],\n'
            '  "create_thread": true/false,\n'
            '  "thread_category": <板块id>,\n'
            '  "thread_topic": "<一句话主题，10-30字>",\n'
            '  "image_thread": true/false,\n'
            '  "like": true/false, "vote": true/false, "welcome": true/false\n'
            "}\n"
            "规则：\n"
            "1. 只能在 candidate_threads 里挑；不要回复自己的帖子和自己的楼层。\n"
            "2. 置顶帖、老用户(u admin_id 很小)的帖子已被告知“可回复: 否”，不要再挑。\n"
            "3. 回复要针对楼层里具体的点，别空泛。\n"
            "4. 没有值得回的就不回（reply_targets 给 []）。\n"
            "5. 同一轮不要超过 3 个目标。\n\n"
            "观察：\n" + json.dumps(digest, ensure_ascii=False, indent=1)
        )
        for _ in range(retries):
            try:
                plan = self.llm.json(prompt, tier="fast", max_tokens=600)
                if plan:
                    return self._normalize_plan(plan)
            except Exception as exc:
                self.log("LLM plan failed: %s" % exc)
        return None

    def _normalize_plan(self, plan):
        allowed = {t["id"]: t for t in self.obs.replyable}
        targets = []
        raw = plan.get("reply_targets") or []
        if isinstance(raw, dict):
            raw = [raw]
        for item in raw[:3]:
            try:
                tid = int(item.get("thread") or 0)
                pid = int(item.get("post") or 0)
            except (TypeError, ValueError, AttributeError):
                continue
            if tid not in allowed:
                self.log("planner target rejected: thread %s" % tid)
                continue
            thread = allowed[tid]
            comments = thread.get('_comments') or []
            if pid:
                match = [c for c in comments if c.get('id') == pid]
                if not match or match[0].get('_own'):
                    continue
                depth = match[0].get('_depth', 0) + 1
                if depth > int(self.cfg.get('max_reply_depth', 3)):
                    continue
            targets.append({'thread': tid, 'post': pid})

        can_post = self.state.daily_count('threads') < self.cfg['daily_post_limit']
        cat = plan.get('thread_category') or (self.cfg['target_categories'] or [2])[0]
        try:
            cat = int(cat)
        except (TypeError, ValueError):
            cat = (self.cfg['target_categories'] or [2])[0]
        if cat not in self.cfg['target_categories']:
            cat = (self.cfg['target_categories'] or [2])[0]

        return {
            "reply_targets": targets,
            "create_thread": bool(plan.get("create_thread")) and can_post,
            "thread_category": cat,
            "thread_topic": str(plan.get("thread_topic") or "")[:120],
            "image_thread": bool(plan.get("image_thread")) and can_post,
            "like": bool(plan.get("like")),
            "vote": bool(plan.get("vote")),
            "welcome": bool(plan.get("welcome")),
        }

    def _heuristic_plan(self):
        o = self.obs
        can_post = self.state.daily_count("threads") < self.cfg["daily_post_limit"]
        candidates = [
            t["id"] for t in o.new_threads
            if len(self.obs.thread_comments.get(t["id"], [])) >= 1
        ] or [t["id"] for t in o.new_threads[:1]]
        rnd = random.random()
        return {
            "reply_comment_ids": candidates[:1] if (candidates and rnd < self.cfg["comment_probability"]) else [],
            "reply_mode": "nested" if rnd > 0.7 else "comment",
            "create_thread": can_post and not o.new_threads and rnd > 0.6,
            "thread_category": None,
            "thread_topic": "",
            "image_thread": can_post and rnd > 0.85 and self.cfg["enable_image_posts"],
            "like": rnd < self.cfg["like_probability"],
            "vote": bool(o.new_threads) and rnd < 0.3,
            "welcome": bool(o.new_threads) and rnd < 0.4 and self.cfg["welcome_newcomers"],
        }

    # ------------------------------------------------ act
    def act(self, plan):
        ran = []
        quiet = self.is_quiet_now()
        if quiet:
            self.log("quiet hours: writes suppressed, local work only")
        slot = plan.get("posting_slot")
        for name, feat in self.features.items():
            if not feat.enabled:
                continue
            try:
                if feat.triggered_by(plan, self):
                    if quiet and name not in self.QUIET_SAFE:
                        self.log("skip %s (quiet hours)" % name)
                        continue
                    n = feat.run(self, plan)
                    if n:
                        ran.append("%s:%s" % (name, n))
                        self.state.log("feature", "%s=%s" % (name, n))
                        time.sleep(random.randint(4, 12))  # human pacing
            except Exception as exc:
                self.log("feature %s crashed: %s" % (name, exc))
                traceback.print_exc()
        if slot and not quiet:
            used = self.state._day_bucket().setdefault("slots", {})
            used[slot] = True
            self.state.log("slot", slot)
        # autonomous workflow: one due task per cycle
        try:
            task, result = self.workflow.execute_one(self)
            if task:
                ran.append("workflow:%s" % task)
        except Exception as exc:
            self.log("workflow crashed: %s" % exc)
        return ran

    # features allowed to run during quiet hours (no forum writes)
    QUIET_SAFE = {"knowledge_learner", "hot_topic_tracker", "content_safety",
                  "url_card", "emoji_enhancer"}

    def reflect(self, ran):
        # mark observation as processed
        for t in self.obs.new_threads:
            self.state.mark_thread(t["id"])
        for tid, c in self.obs.new_comments:
            if c.get("id"):
                self.state.mark_post(c["id"])
        # daily memory diary (retention of the full decision flow)
        try:
            self.memory.daily_summary(
                self.state.data.get("stats", {}),
                [truncate(t, 16) for t in self.obs.hot_titles[:6]])
        except Exception:
            pass
        self.state.save()
        self.log("cycle done: %s" % (", ".join(ran) if ran else "nothing to do"))

    # ------------------------------------------------ master session
    MASTER_STEPS = 6

    def _observation_context(self):
        o = self.obs
        rows = ["Today: %s | quiet_hours_now: %s | quota threads %s/%s "
                "comments %s/%s"
                % (_today(), self.is_quiet_now(),
                   self.state.daily_count("threads"),
                   self.cfg["daily_post_limit"],
                   self.state.daily_count("comments"),
                   self.cfg.get("daily_comment_limit", 8))]
        for t in o.replyable[:6]:
            rows.append("thread id=%s | %s | replies=%s | floors=%s"
                        % (t.get("id"), truncate(t.get("title", ""), 36),
                           t.get("reply_count"),
                           len(t.get("_comments") or [])))
        if o.mention_hits:
            rows.append("mentions: %s" % len(o.mention_hits))
        return "\n".join(rows)

    def master_session(self, max_steps=None):
        """LLM-mastered phase: multi-step tool use, then a wrap-up."""
        max_steps = max_steps or self.MASTER_STEPS
        self.refresh_skills()
        sys_text = self.llm.system(
            "You are the autonomous master agent of the mk49.top forum "
            "account. You have a full tool belt (forum reads/writes, image "
            "generation, web browsing, files, shell, scheduling, memory). "
            "This cycle you may act directly through tools. Guidelines: "
            "1) check forum_read_inbox and answer what deserves an answer; "
            "2) optionally comment on interesting threads or start the "
            "scheduled thread; 3) use mem_write for anything worth "
            "remembering; 4) be economical: 1-4 tool calls is usually "
            "enough; 5) never reveal being a bot; 6) night quiet hours "
            "block writes automatically. Finish with a one-line summary.")
        messages = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content":
                "Current observation:\n" + self._observation_context()},
        ]
        reg = self.registry
        actions = 0
        for _step in range(max_steps):
            try:
                msg = self.llm.chat_raw(messages, tier="smart",
                                        max_tokens=900, tools=reg.schemas())
            except Exception as exc:
                self.log("master LLM failed: %s" % exc)
                break
            calls = msg.get("tool_calls") or []
            if not calls:
                self.state.log("master", (msg.get("content") or "")[:200])
                break
            messages.append({"role": "assistant",
                             "content": msg.get("content") or "",
                             "tool_calls": calls})
            for call in calls[:3]:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    import json as _json
                    args = _json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = reg.dispatch(self, name, args)
                actions += 0 if out.startswith("ERROR") else 1
                messages.append({"role": "tool",
                                 "tool_call_id": call.get("id"),
                                 "content": out[:1500]})
                self.log("tool %s -> %s" % (name, out[:90]))
        return actions

    def run_cycle(self):
        self.observe()
        plan = self.decide()
        ran = self.act(plan)
        # LLM-mastered autonomous phase (skipped during quiet hours)
        if not self.is_quiet_now():
            try:
                n = self.master_session()
                if n:
                    ran.append("master:%s" % n)
            except Exception as exc:
                self.log("master session crashed: %s" % exc)
        self.reflect(ran)
        return ran

    def run_forever(self, interval=None):
        interval = interval or self.cfg["scan_interval"]
        while True:
            wrote = []
            try:
                self.observe()
                plan = self.decide()
                wrote = self.act(plan)
                self.reflect(wrote)
            except Exception as exc:
                self.log("cycle error: %s" % exc)
                traceback.print_exc()
                try:
                    self.client.login()
                except Exception:
                    pass
            # adaptive sleep: longer after real activity, jitter for humanity
            base = interval * (1.6 if wrote else 1.0)
            jitter = random.randint(0, max(60, interval // 6))
            nap = base + jitter
            self.log("sleeping %.0fs" % nap)
            time.sleep(nap)

"""Independent chat-room reply agent (lobby + private DMs).

Runs as its own loop/process; shares State/memory-notes + KnowledgeBase
(system prompt) with the forum agent through the same build_agent().
Image ops auto-sleep on timeout instead of failing the cycle."""
import random
import time
import traceback

CHAT_BASE = "https://forum.mk49.top/bbs/chat"
# conversations the agent must never reply to (own threads / test convs)
SKIP_CONV = {26}

# min seconds between writes per conversation (server trips at ~4 fast)
SEND_GAP = 1.4


def _with_retry(fn, what, tries=3, base_sleep=3.0, log=None):
    """Run fn(); on timeout/network error sleep and retry (auto-wait)."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:
            last = exc
            msg = str(exc)
            transient = any(k in msg for k in (
                "Timeout", "timed out", "Connection", "reset", "502", "503",
                "504"))
            if not transient or i == tries - 1:
                break
            nap = base_sleep * (i + 1) + random.uniform(0.5, 2.0)
            if log:
                log("%s timeout/failure, auto-sleep %.1fs then retry %d/%d"
                    % (what, nap, i + 2, tries))
            time.sleep(nap)
    if log:
        log("%s FAILED after %d tries: %s" % (what, tries, str(last)[:140]))
    raise last if last else RuntimeError(what + " failed")


def _chat_req(agent, method, path, body=None, files=None, timeout=40):
    """HTTP call with auto-sleep retry (delegates to chat module)."""
    from mk49.tools.chat import _req
    return _req(method, agent.client.token, path, body=body, files=files,
                 timeout=timeout, tries=3, gap=True)


def _msgs(agent, conv_id, channel=None, limit=40):
    cid = int(conv_id)
    ch = int(channel) if channel else (1 if cid == 1 else None)
    path = "conversations/%d/messages" % cid
    if ch:
        path += "?channel=%d" % ch
    r = _chat_req(agent, "GET", path, timeout=30)
    d = (r.get("data") or {}).get("data") or {}
    items = d.get("items") or [] if isinstance(d, dict) else []
    return items[: max(1, int(limit))]


def _unread_convs(agent):
    r = _chat_req(agent, "GET", "conversations", timeout=30)
    d = (r.get("data") or {}).get("data") or {}
    items = d.get("items") if isinstance(d, dict) else []
    return items or []


def _last_seen(agent):
    return agent.state.data.setdefault("chat_last_seen", {})


class ChatAgent:
    """Independent loop: reads chat -> LLM decides replies -> sends.

    Shares State (memory notes) + KnowledgeBase (prompt) with the forum
    agent via the parent Agent object (same file handles, same dict)."""

    def __init__(self, agent):
        self.agent = agent
        self.llm = agent.llm
        self.state = agent.state
        self.cfg = agent.cfg
        # per-conversation last send timestamp (pacing)
        self._sent_at = {}

    # ---------- gates ----------
    def _quiet(self):
        return self.agent.is_quiet_now()

    def _pace(self, conv):
        last = self._sent_at.get(conv, 0.0)
        wait = SEND_GAP - (time.time() - last)
        if wait > 0:
            time.sleep(wait)

    # ---------- memory (shared with forum agent) ----------
    def _remember(self, text, conv, who, kind="chat"):
        notes = self.state.data.setdefault("notes", [])
        notes.append({
            "id": "chat%d" % int(time.time() * 1000 % 1e8),
            "ts": time.time(),
            "text": "[%s] conv %s %s: %s" % (kind, conv, who, text[:200]),
            "tags": ["chat", kind],
            "links": [],
        })
        if len(notes) > 400:
            del notes[: len(notes) - 400]

    def _kb_digest(self):
        """Shared knowledge digest injected into chat decisions."""
        kb_text = self.agent.llm.knowledge_text or ""
        return kb_text[:1200]

    # ---------- LLM decision ----------
    def _decide(self, conv, who, msgs, is_lobby):
        recent = []
        for m in msgs[-14:]:
            if m.get("deleted_at"):
                continue
            recent.append("%s: %s" % (m.get("sender_name") or "?",
                                     (m.get("body") or "").strip()[:160]))
        history = "\n".join(recent)
        scope = ("聊天室大厅（多人频道）" if is_lobby
                 else "私聊（1对1：%s）" % who)
        prompt = (
            "你是论坛驻场账号「幻想ai」，现在在%s里聊天。"
            "风格：短句、口语、像真人随口接话，别每句都客套，"
            "别像客服；可玩梗可反问；不写长段。"
            "只输出你这一句要发的话（不要引号、不要解释）。\n\n"
            "%s\n\n最近对话：\n%s\n"
            "（若没人找你或与你无关，只输出一个横杠 - 表示不回）"
            % (scope, self._kb_digest(), history))
        try:
            out = self.llm.text(prompt, tier="fast", max_tokens=160,
                                temperature=0.9)
        except Exception as exc:
            print("[chat] LLM decide failed: %s" % str(exc)[:140])
            return None
        out = (out or "").strip()
        if not out or out in ("-", "—", "－"):
            return None
        # strip quotes / preambles
        for pre in ("回复：", "我回：", "\"", "'", "「", "」"):
            if out.startswith(pre):
                out = out[len(pre):].strip()
        if len(out) > 300:
            out = out[:300]
        if not out:
            return None
        # lobby: must reference something recent (weak relevance filter)
        if is_lobby and len(recent) >= 3:
            tail_words = set("".join(recent[-4:]))
            if not any(w in out for w in ("？", "?", "哈哈", "6", "是",
                                          "啊", "吧", "呢")) and \
               len(out) < 4:
                return None
        return out

    # ---------- send ----------
    def _send(self, conv, text, channel=None, reply_to=None):
        self._pace(conv)
        cid = int(conv)
        ch = int(channel) if channel else (1 if cid == 1 else None)
        path = "conversations/%d/messages" % cid
        if ch:
            path += "?channel=%d" % ch
        import uuid
        body = {"body": text[:400], "clientId": uuid.uuid4().hex}
        if reply_to:
            body["replyTo"] = int(reply_to)
        r = _chat_req(agent=self.agent, method="POST", path=path, body=body)
        d = (r.get("data") or {}).get("data") or {}
        ok = r.get("status") == 200 and isinstance(d, dict) and d.get("id")
        if ok:
            self._sent_at[cid] = time.time()
            self.state.log("chat_reply", "conv=%d msg=%s text=%s"
                           % (cid, d.get("id"), text[:50]))
            self.state.stat_bump("chat_replies")
        return ok, d.get("id") if ok else None

    # ---------- one conversation pass ----------
    def _handle_conv(self, conv, title, is_lobby, unread):
        if conv in SKIP_CONV:
            return 0
        if self._quiet():
            # quiet hours: remember only, never send
            try:
                msgs = _msgs(self.agent, conv, limit=12)
                for m in msgs[-6:]:
                    who = m.get("sender_name") or "?"
                    if str(m.get("sender_id") or m.get("sender")) == \
                            str(self.agent.client.user_id):
                        continue
                    txt = (m.get("body") or "").strip()
                    if txt:
                        self._remember(txt, conv, who,
                                       "dm" if not is_lobby else "lobby")
            except Exception:
                pass
            return 0
        try:
            msgs = _msgs(self.agent, conv, limit=40)
        except Exception as exc:
            print("[chat] read conv %s failed: %s" % (conv, str(exc)[:120]))
            return 0
        if not msgs:
            return 0
        uid = str(self.agent.client.user_id)
        # last message mine? -> stay quiet unless mentioned
        last = msgs[-1]
        last_uid = str(last.get("sender_id") or last.get("sender") or "")
        target = None
        who = "?"
        if is_lobby:
            # reply only if someone spoke after my last message
            seen = _last_seen(self.agent)
            last_seen_id = int(seen.get(str(conv), 0))
            new = [m for m in msgs if int(m.get("id") or 0) > last_seen_id
                   and str(m.get("sender_id") or m.get("sender") or "") != uid]
            if not new:
                # just record position, no reply
                seen[str(conv)] = int(msgs[-1].get("id") or 0)
                return 0
            # only reply to the newest unseen burst
            target = new[-1]
            who = target.get("sender_name") or "?"
            # rate: lobby max 1 reply per visit + daily cap via state
            if self.state.daily_count("chat_lobby") >= \
                    int(self.cfg.get("daily_chat_lobby", 30)):
                seen[str(conv)] = int(msgs[-1].get("id") or 0)
                return 0
        else:
            if last_uid == uid:
                return 0
            who = last.get("sender_name") or "?"
            if self.state.daily_count("chat_dm") >= \
                    int(self.cfg.get("daily_chat_dm", 40)):
                return 0
        text = self._decide(conv, who, msgs, is_lobby)
        # remember everything we saw (shared memory)
        for m in (msgs[-6:] if is_lobby else msgs[-3:]):
            if str(m.get("sender_id") or m.get("sender") or "") == uid:
                continue
            t = (m.get("body") or "").strip()
            if t:
                self._remember(t, conv, m.get("sender_name") or "?",
                               "lobby" if is_lobby else "dm")
        if not text:
            if is_lobby:
                _last_seen(self.agent)[str(conv)] = \
                    int(msgs[-1].get("id") or 0)
            return 0
        # quiet re-check just before write
        if self._quiet():
            return 0
        # lobby replies quote the triggering message
        rid = int(target.get("id")) if (is_lobby and target) else \
            (int(last.get("id")) if not is_lobby and unread else None)
        ok, mid = self._send(conv, text, channel=(1 if is_lobby else None),
                              reply_to=rid if ok_needs_reply(is_lobby, unread)
                              else None)
        if is_lobby:
            _last_seen(self.agent)[str(conv)] = int(msgs[-1].get("id") or 0)
        if ok and not is_lobby:
            self.state.bump_daily("chat_dm")
            self.state.stat_bump("chat_replies")
        if ok and is_lobby:
            self.state.bump_daily("chat_lobby")
        return 1 if ok else 0

    # ---------- cycle ----------
    def run_cycle(self):
        # hot-reload shared knowledge into prompt (forum agent's
        # kb_add/edit/delete show up here too)
        try:
            self.agent.refresh_skills()
        except Exception:
            pass
        sent = 0
        try:
            convs = _unread_convs(self.agent)
        except Exception as exc:
            print("[chat] list convs failed: %s" % str(exc)[:120])
            return 0
        # lobby first (id=1), then DMs with unread, then quiet capture
        ordered = sorted(convs, key=lambda c: (0 if c.get("is_lobby")
                                               else 1))
        for c in ordered:
            conv = c.get("id")
            if conv in SKIP_CONV:
                continue
            is_lobby = bool(c.get("is_lobby"))
            unread = int(c.get("unread") or 0)
            if not is_lobby and unread <= 0 and not self._quiet():
                continue
            try:
                sent += self._handle_conv(conv, c.get("title"), is_lobby,
                                          unread)
            except Exception as exc:
                print("[chat] conv %s error: %s" % (conv, str(exc)[:140]))
        # DMs from operator are urgent: always scan even if unread=0? handled
        self.state.autosave()
        return sent

    def run_forever(self, interval=None):
        interval = interval or int(self.cfg.get("chat_scan_interval", 90))
        self.agent.log("chat-agent loop start (interval=%ds, quiet=%s)"
                       % (interval, "on" if self._quiet() else "off"))
        while True:
            wrote = 0
            try:
                wrote = self.run_cycle()
            except Exception as exc:
                self.agent.log("chat cycle error: %s" % exc)
                traceback.print_exc()
                try:
                    self.agent.client.login()
                except Exception:
                    pass
            nap = interval * (1.7 if wrote else 1.0) + \
                random.randint(0, max(20, interval // 5))
            self.agent.log("chat sleeping %.0fs (sent=%d)" % (nap, wrote))
            time.sleep(nap)


def ok_needs_reply(is_lobby, unread):
    # lobby: always quote the triggering message; DM: quote only if unread
    return True if is_lobby else bool(unread)

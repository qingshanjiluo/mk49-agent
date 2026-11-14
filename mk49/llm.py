import json
import os

import requests

from .config import load_config

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS = os.path.join(HERE, "prompts")
DEFAULT_MODELS = os.path.join(HERE, "models.json")


class LLMError(Exception):
    """Raised when every configured model channel fails."""


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def load_prompt(name):
    return read_text(os.path.join(PROMPTS, name + ".txt")).strip()


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def credentials_refs(name=".credentials.yaml"):
    """Read the refs: map out of DSH's credential file."""
    import re
    cand = os.path.join(os.path.expanduser("~"), ".dsh", name)
    if not os.path.isfile(cand):
        return {}
    out, in_refs = {}, False
    with open(cand, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            if re.match(r"^refs\s*:\s*$", raw):
                in_refs = True
                continue
            if in_refs:
                if raw.strip() and not raw.startswith(" "):
                    in_refs = False
                    continue
                m = re.match(r"^\s+([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$", raw)
                if m:
                    out[m.group(1)] = m.group(2).strip().strip("'").strip('"')
    return out


def resolve_gateway_key(env_name, cred_file):
    val = os.getenv(env_name)
    if not val:
        val = credentials_refs(cred_file).get(env_name)
    return (val or "").strip()


PERSONA_FILES = ("persona.txt", "persona_game.txt")


class ChatClient:
    def __init__(self, timeout=120, models_path=DEFAULT_MODELS):
        self.models_path = models_path
        self.cfg = load_config()
        self.models = read_json(models_path)
        base = self.models.get("gateway") or "https://ai.furry.vg/v1"
        self.base_url = base.rstrip("/")
        self.key = resolve_gateway_key(
            self.models.get("gateway_key_env") or "FURRY_API_KEY",
            self.models.get("credential_file") or ".credentials.yaml",
        )
        if not self.key:
            raise LLMError("no gateway key: set FURRY_API_KEY or .credentials.yaml refs")

        chain = list(self.models.get("model_chain") or self.models.get("chat_models") or [])
        smart = (self.models.get("smart_model")
                 or (chain[0] if chain else "selfdeploy/deepseek-v4.1-flash-free"))
        fast = self.models.get("fast_model") or smart
        self.smart_model = smart
        self.fast_model = fast
        order = [smart, fast] + chain
        self.chain = list(dict.fromkeys([m for m in order if m]))

        self.temp_smart = float(self.models.get("temperature_smart", 0.85))
        self.temp_fast = float(self.models.get("temperature_fast", 0.4))
        self.timeout = timeout
        self.persona = self._load_persona()
        self.knowledge_text = ""
        self.session = requests.Session()
        self.session.trust_env = False

    # ------------- persona -------------
    def _load_persona(self):
        parts = []
        for fn in PERSONA_FILES:
            key = fn.split(".")[0] + "_file"
            txt = read_text(self.cfg.get(key) or os.path.join(HERE, fn)).strip()
            if txt:
                parts.append(txt)
        return "\n\n".join(parts)

    def system(self, extra=""):
        parts = [p for p in (self.persona, (self.knowledge_text or "").strip())
                 if p]
        parts.append((extra or "").strip())
        parts = [p for p in parts if p]
        return "\n\n".join(parts)

    # ------------- transport -------------
    def _post(self, model, messages, temperature, max_tokens, json_mode):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": "Bearer " + self.key,
                   "Content-Type": "application/json"}
        r = self.session.post(self.base_url + "/chat/completions",
                              headers=headers, json=payload,
                              timeout=self.timeout)
        if r.status_code >= 400:
            raise LLMError("HTTP %s %s" % (r.status_code, r.text[:160]))
        data = r.json()
        if "error" in data:
            raise LLMError(str(data["error"])[:200])
        msg = data["choices"][0]["message"]
        return (msg.get("content") or "").strip()

    # ------------- public chat API -------------
    def chat(self, messages, *, tier="smart", temperature=None,
             max_tokens=900, json_mode=False):
        first = self.smart_model if tier == "smart" else self.fast_model
        order = [first] + list(self.chain)
        temp = (self.temp_smart if tier == "smart" else self.temp_fast) \
            if temperature is None else temperature
        last_err = None
        for model in dict.fromkeys(order):
            try:
                out = self._post(model, messages, temp, max_tokens, json_mode)
                if out:
                    return out
                last_err = "empty content from %s" % model
            except Exception as exc:
                last_err = "%s: %s" % (model, str(exc)[:140])
        raise LLMError("all models failed: %s" % last_err)

    def chat_raw(self, messages, *, tier="smart", temperature=None,
                 max_tokens=900, tools=None):
        """Function-calling variant: returns the full assistant message
        dict (content + tool_calls) instead of only the text."""
        first = self.smart_model if tier == "smart" else self.fast_model
        order = [first] + list(self.chain)
        temp = (self.temp_smart if tier == "smart" else self.temp_fast) \
            if temperature is None else temperature
        payload_base = {
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload_base["tools"] = tools
            payload_base["tool_choice"] = "auto"
        last_err = None
        for model in dict.fromkeys(order):
            payload = dict(payload_base, model=model)
            try:
                headers = {"Authorization": "Bearer " + self.key,
                           "Content-Type": "application/json"}
                r = self.session.post(self.base_url + "/chat/completions",
                                      headers=headers, json=payload,
                                      timeout=self.timeout)
                if r.status_code >= 400:
                    raise LLMError("HTTP %s %s"
                                   % (r.status_code, r.text[:160]))
                data = r.json()
                if "error" in data:
                    raise LLMError(str(data["error"])[:200])
                return data["choices"][0]["message"] or {}
            except Exception as exc:
                last_err = "%s: %s" % (model, str(exc)[:140])
        raise LLMError("chat_raw failed on all models: %s" % last_err)

    def text(self, prompt, *, system=None, tier="smart",
             temperature=None, max_tokens=900):
        msgs = []
        sys_text = self.system(system or "")
        if sys_text:
            msgs.append({"role": "system", "content": sys_text})
        msgs.append({"role": "user", "content": prompt})
        return self.chat(msgs, tier=tier, temperature=temperature,
                         max_tokens=max_tokens)

    def json(self, prompt, *, system=None, tier="fast", max_tokens=500,
             temperature=0.2, json_mode=False):
        extra = (system or "")
        raw = self.text(prompt, system=extra, tier=tier,
                        temperature=temperature, max_tokens=max_tokens)
        return extract_json(raw)

    # ------------- authored forum content (smart tier) -------------
    def _floor_lines(self, recent):
        rows = []
        for c in (recent or [])[-8:]:
            rows.append("#%s %s：%s" % (c.get("floor"), c.get("author"), c.get("text")))
        return "\n".join(rows) if rows else "（暂无楼层）"

    def continue_thread(self, title, body, recent=None, *, my_nickname="",
                        category="", already_said=0, meta=""):
        """First-level comment on a thread, grounded in its metadata."""
        already = ""
        if already_said:
            already = "注意：你已经在这个帖子里回过 %d 次了，这次不要再重复自己的观点。" % already_said
        prompt = (
            "现在论坛有一个帖子，你要以普通玩家身份去回它。\n\n"
            "帖子元数据：" + (meta or "无") + "\n"
            "所属板块：" + (category or "未知") + "\n"
            "标题：" + (title or "（无）") + "\n"
            "正文（节选）：\n" + (body or "（无）")[:900] + "\n\n"
            "已有楼层：\n" + self._floor_lines(recent) + "\n"
            + already + "\n"
            "任务：写一条回复这个帖子的评论。要求：\n"
            "1. 长度模仿真人：多数回帖就 3~30 字，想到什么说一句；"
            "只有真有干货值得展开才写长（最多 120 字）；\n"
            "2. 必须接住帖子里具体的内容（提到的船、操作、事件、梗），"
            "可以补充自己的经验、观点，或问一个真问题；\n"
            "3. 不复读楼主原话，不说空话（如“支持”“说得好”），"
            "不逐条罗列，不用标题和 markdown 结构；\n"
            "4. 不提自己是 AI 或机器人。\n"
            "只输出评论正文。"
        )
        return self.text(prompt, tier="smart", max_tokens=600)

    def reply_to_comment(self, title, parent, *, context="", chain="",
                         my_nickname="", category="", meta="", style=None):
        """Reply to one comment (used for mentions and simple nested replies)."""
        prompt = (
            "你在论坛「龙之归宿」回帖。你的马甲：「" + (my_nickname or "") + "」。\n"
            + ("所属板块：" + category + "\n" if category else "")
            + ("帖子元数据：" + meta + "\n" if meta else "")
            + "帖子标题：" + (title or "（无）") + "\n"
            + ("帖子正文摘要：" + context[:400] + "\n" if context else "")
            + ("对话链（谁回谁）：" + chain + "\n" if chain else "")
            + "你要回复的这一楼：" + (parent or "") + "\n\n"
            "任务：写一条直接回应这一楼的回复。要求：\n"
            "1. 长度像真人斗嘴：经常就几个字到 30 字（哈？/确实/这不扯吗），"
            "最多不超过 100 字；\n"
            "2. 只接对方这句话里的具体点（他说的船/操作/观点/情绪），"
            "可以赞同、反驳、补充、玩梗或反问；\n"
            "2. 口语自然像真人玩家，不要另起话题，不要总结帖主，不用 markdown 结构；\n"
            "3. 不提自己是 AI 或机器人。\n"
            + ((style or "") + "\n" if style else "")
            + "只输出回复正文。"
        )
        return self.text(prompt, tier="smart", max_tokens=500)

    def reply_to_reply(self, thread_title, thread_body, parent_text, *,
                       chain="", my_nickname="", category="", meta=""):
        """Nested reply inside a 楼中楼 chain."""
        return self.reply_to_comment(
            thread_title, parent_text,
            context=(thread_body or "")[:400], chain=chain,
            my_nickname=my_nickname, category=category, meta=meta,
        )

    def new_thread_title(self, category_name, topics, history=None):
        prompt = (
            "你要在论坛「龙之归宿」的「" + (category_name or "聊天") + "」板块发新帖。\n"
            "近期板块热门话题：" + "、".join(list(topics or [])[:8]) + "\n"
            + (("这些标题已经用过，别重复：" + " | ".join(list(history)[:8]) + "\n") if history else "")
            + "\n任务：想一个普通玩家会用的帖子标题。要求：\n"
            "1. 像人话，有具体内容（什么游戏/什么船/什么事）；\n"
            "2. 14 字以内；\n"
            "3. 不当标题党，不用“聊聊XXX”这种空泛格式，不涉政。\n"
            "只输出标题本身，不要引号，不要解释。"
        )
        return _clean_title(self.text(prompt, tier="smart", max_tokens=80))

    def new_thread_body(self, title, topic, extra=""):
        prompt = (
            "你在论坛「龙之归宿」发帖。\n"
            "标题：" + (title or "") + "\n"
            "主题方向：" + (topic or "") + "\n\n"
            "任务：写帖子正文，150~400 字。要求：\n"
            "1. 口语化、有观点或有干货，像老玩家写的；\n"
            "2. 可以用 markdown 美化排版：列表、> 引用、**加粗**、--- 分隔线；"
            "涉及命令/配置/数据时用 ``` 代码块；\n"
            "3. 不涉政、不涉黄、不广告、不暴露 AI 身份。\n"
            + (extra + "\n" if extra else "")
            + "只输出正文。"
        )
        return self.text(prompt, tier="smart", max_tokens=800)

    def image_prompt_for(self, topic, title=""):
        prompt = (
            "把下面的中文内容改写成一句英文的文生图提示词（image prompt）。\n"
            "主题：" + (topic or "") + "\n"
            "标题：" + (title or "") + "\n"
            "要求：画面具体、有氛围；不含中文；不超过 60 词；安全无害。\n"
            "只输出英文提示词。"
        )
        return self.text(prompt, tier="smart", max_tokens=160)


# ---------------- module-level helpers ----------------

TITLE_JUNK = (
    "标题：", "标题:", "用户要求", "为论坛板块", "只输出", "不要引号",
    "不要解释", "请为", "想一个", "12字以内", "15字以内", "14字以内",
)


def extract_json(raw):
    """Best-effort JSON object out of a model reply."""
    if not raw:
        return {}
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
    try:
        return json.loads(text)
    except ValueError:
        return {}


def _clean_title(raw):
    """Strip prompt echo / wrappers so a title never reads like instructions."""
    text = (raw or "").strip()
    text = text.strip("`*# ")
    text = text.strip("\"“”‘’「」『』《》[]()")
    for prefix in ("标题：", "标题:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    for junk in TITLE_JUNK:
        if junk in text:
            return ""
    for stop in ("\n", "。", "；", ";", "，"):
        idx = text.find(stop)
        if idx > 0:
            text = text[:idx]
            break
    text = text.strip().strip("\"“”「」《》")
    return text[:40] if text else ""


import re  # noqa: E402  (used by extract_json / _clean_title above)






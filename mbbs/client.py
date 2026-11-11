"""MBBS (forum.mk49.top) HTTP client.

Covers every endpoint family discovered from the SPA bundle:
auth / threads / posts / comments / polls / resources / users / messages /
categories / groups / emojis / tags / series / settings / moderation.
"""

import base64
import io
import json
import os
import re
import time

import requests

RESOURCE_BASE = "/resources/"


class MBBSAuthError(Exception):
    pass


class MBBSAPIError(Exception):
    def __init__(self, message, status=None, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def _parse_retry_after(text):
    """Extract N from '请求过于频繁，请在 N 秒后重试' style messages."""
    m = re.search(r"(\d+)\s*秒", text or "")
    return int(m.group(1)) if m else None


def _parse_retry_after(text):
    """Extract N from '请求过于频繁，请在 N 秒后重试' style messages."""
    m = re.search(r"(\d+)\s*秒", text or "")
    return int(m.group(1)) if m else None


class MBBSClient:
    def __init__(self, base_url, username="", password="", timeout=20):
        base_url = (base_url or "").rstrip("/")
        # Accept either origin (https://forum.mk49.top) or API root
        # (https://forum.mk49.top/bbs); normalise to the API root.
        if not base_url.endswith("/bbs"):
            base_url += "/bbs"
        self.base_url = base_url
        self.api_base = base_url
        self.origin = base_url[:-len("/bbs")]
        self.username = username
        self.password = password
        self.timeout = timeout
        self.token = None
        self.user = None
        self.user_id = None
        self.session = requests.Session()
        self.session.trust_env = False  # ignore system SOCKS proxy
        self._ocr = None
        self._login_lock_free()

    # ---------------- helpers ----------------
    def _login_lock_free(self):
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Origin": self.origin,
                "Referer": self.origin + "/",
            }
        )

    def _auth_headers(self):
        h = {}
        if self.token:
            h["authorization"] = self.token
        if self.user_id:
            h["mbbs-userid"] = str(self.user_id)
        return h

    def _resolve(self, path):
        if path.startswith("http"):
            return path
        return self.api_base + "/" + path.lstrip("/")

    def request(self, method, path, *, params=None, json_body=None, files=None,
                retry_auth=True):
        """Low level request. Returns parsed JSON (dict). Raises MBBSAPIError."""
        url = self._resolve(path)
        headers = self._auth_headers()
        if files is None and json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            resp = self.session.request(
                method, url,
                params=params, json=json_body, files=files, headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MBBSAPIError("network error: %s" % exc)

        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if payload is None:
            if resp.status_code >= 400:
                raise MBBSAPIError("HTTP %s" % resp.status_code, resp.status_code)
            return {"success": True, "data": resp.text}

        if resp.status_code == 401 or (
            payload.get("success") is False
            and "登录" in str(payload.get("message", ""))
            and retry_auth
        ):
            # token expired -> re-login once
            if retry_auth and self.login():
                return self.request(method, path, params=params,
                                    json_body=json_body, files=files,
                                    retry_auth=False)
            raise MBBSAuthError(str(payload.get("message") or "unauthorized"))

        if payload.get("success") is False:
            msg = str(payload.get("message") or "request failed")
            wait = _parse_retry_after(msg)
            if wait:
                time.sleep(min(wait + 1, 300))
                return self.request(method, path, params=params,
                                    json_body=json_body, files=files,
                                    retry_auth=retry_auth)
            raise MBBSAPIError(msg, resp.status_code, payload)
        return payload

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, json_body=body, **kw)

    # ---------------- auth ----------------
    def _ocr_instance(self):
        if self._ocr is None:
            try:
                import ddddocr
                self._ocr = ddddocr.DdddOcr(show_ad=False)
            except Exception as exc:  # pragma: no cover - optional dep
                print("[login] ddddocr unavailable: %s" % exc)
                self._ocr = False
        return self._ocr or None

    @staticmethod
    def _png_from_svg(svg_text):
        try:
            import cairosvg
            return cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                                    output_width=300, output_height=100, dpi=200)
        except Exception:
            return None

    def _fetch_captcha(self):
        data = self.get("login/captcha").get("data") or {}
        cid, svg, image = data.get("id"), data.get("svg"), data.get("image")
        if image and str(image).startswith("data:"):
            raw = base64.b64decode(str(image).split(",", 1)[1])
            return cid, raw, "png"
        if svg:
            raw = self._png_from_svg(svg)
            if raw:
                return cid, raw, "svg"
        return None, None, None

    @staticmethod
    def _normalize(text):
        return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()

    def _recognize_captcha(self, raw):
        ocr = self._ocr_instance()
        if not ocr:
            return ""
        try:
            return self._normalize(ocr.classification(raw))
        except Exception as exc:
            print("[login] captcha ocr failed: %s" % exc)
            return ""

    def login(self, max_attempts=50):
        """Captcha OCR login loop. Returns True on success."""
        for attempt in range(1, max_attempts + 1):
            cid, raw, kind = None, None, None
            try:
                cid, raw, kind = self._fetch_captcha()
            except MBBSAPIError as exc:
                wait = _parse_retry_after(str(exc))
                if wait:
                    print("[login] rate limited, sleeping %ds" % wait)
                    time.sleep(min(wait + 1, 300))
                    continue
                print("[login] captcha fetch failed: %s" % exc)
                time.sleep(2)
                continue
            text = self._recognize_captcha(raw)
            if not text:
                # fallback: try vision-independent upscale
                text = self._recognize_captcha(self._upscale(raw))
            if not text:
                continue
            try:
                payload = self.post(
                    "login",
                    {
                        "username": self.username,
                        "password": self.password,
                        "captcha_id": cid,
                        "captcha_text": text,
                    },
                )
            except MBBSAPIError as exc:
                wait = _parse_retry_after(str(exc))
                if wait:
                    print("[login] rate limited, sleeping %ds" % wait)
                    time.sleep(min(wait + 1, 300))
                    continue
                msg = str(exc)
                if "验证码" in msg or "captcha" in msg.lower():
                    continue
                print("[login] rejected: %s" % msg)
                time.sleep(1)
                continue
            data = payload.get("data") or {}
            if data.get("token"):
                self.token = data.get("token")
                self.user = data
                self.user_id = data.get("id")
                print("[login] ok as %s (id=%s) attempt=%d"
                      % (data.get("username"), self.user_id, attempt))
                return True
        print("[login] failed after %d attempts" % max_attempts)
        return False

    if False:  # placeholder to keep structure tidy
        pass

    @staticmethod
    def _unused():  # pragma: no cover
        return None

    @staticmethod
    def _upscale(raw):
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return raw

    def ensure_login(self):
        if self.token and self.user_id:
            return True
        return self.login()

    # ---------------- users ----------------
    def me(self):
        return self.get("/users/getLoginUser").get("data")

    def get_user(self, user_id):
        return self.get("/users/%s" % user_id).get("data")

    def get_user_by_name(self, name):
        return self.get("/users/getByName", params={"name": name}).get("data")

    def list_users(self, page_limit=20, page_offset=0, search=""):
        params = {"page_limit": page_limit, "page_offset": page_offset}
        if search:
            params["search"] = search
        payload = self.get("/users/list", params=params)
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

    def user_permissions(self, group_id):
        return self.get("/permissions/getPermissions", params={"group_id": group_id}) \
                   .get("data") or []

    # ---------------- categories / meta ----------------
    def categories(self):
        return self.get("category/listCategory").get("data") or []

    def groups(self):
        return self.get("group/listGroup").get("data") or []

    def identities(self):
        return self.get("identity/listIdentity").get("data") or []

    def emojis(self):
        return self.get("emoji/listEmoji").get("data") or []

    def all_tags(self):
        try:
            return self.get("threadTag/listAllTag").get("data") or []
        except MBBSAPIError:
            return []

    def editable_tags_for_category(self, category_id=None):
        if category_id is None:
            path = "threadTag/listEditableTagForAllCategory"
        else:
            path = "threadTag/listEditableTagForCategory"
            return self.get(path, params={"category_id": category_id}).get("data") or []
        return self.get(path).get("data") or []

    # ---------------- threads ----------------
    def list_threads(self, category_id=None, page_limit=20, page_offset=0,
                      sort="-created_at", keywords=None, user_id=None, **extra):
        params = {"page_limit": page_limit, "page_offset": page_offset, "sort": sort}
        if category_id is not None:
            params["category_id"] = category_id
        if keywords:
            params["keywords"] = keywords
        if user_id:
            params["user_id"] = user_id
        params.update(extra)
        payload = self.get("threads/list", params=params)
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

    def thread_detail(self, thread_id):
        return self.get("threads/%s" % thread_id).get("data")

    def create_thread(self, category_id, title, content, *, is_draft=False,
                      series_id=None, polls=None):
        body = {"category_id": category_id, "title": title, "content": content}
        if is_draft:
            body["is_draft"] = True
        if series_id is not None:
            body["series_id"] = series_id
        if polls:
            body["polls"] = polls
        return self.post("threads/create", body).get("data")

    def modify_thread(self, thread_id, **fields):
        """POST threads/{id} — edit title/content/category/series/draft/polls."""
        return self.post("threads/%s" % thread_id, fields).get("data")

    def delete_thread(self, thread_id):
        return self.request("DELETE", "threads/%s" % thread_id).get("data")

    def restore_thread(self, thread_id):
        return self.post("threads/restoreDelete?thread_id=%s" % thread_id).get("data")

    def move_thread(self, thread_id, category_id):
        return self.post("threads/%s/move" % thread_id,
                         {"category_id": category_id}).get("data")

    def batch_delete_threads(self, thread_ids):
        return self.post("threads/batchDelete", {"thread_ids": thread_ids}).get("data")

    def set_essence(self, thread_id, is_essence=True):
        return self.post("threads/setEssence",
                         {"thread_id": thread_id, "is_essence": is_essence}).get("data")

    def set_sticky(self, thread_id, is_sticky=True):
        return self.post("threads/setSticky",
                         {"thread_id": thread_id, "is_sticky": is_sticky}).get("data")

    def set_approved(self, thread_id, is_approved=True):
        return self.post("threads/setApproved",
                         {"thread_id": thread_id, "is_approved": is_approved}).get("data")

    def set_disable_post(self, thread_id, disable=True):
        return self.post("threads/setDisablePost",
                         {"thread_id": thread_id, "disable_post": disable}).get("data")

    def approve_with_user_group(self, thread_id):
        return self.post("threads/approveWithUserGroup",
                         {"thread_id": thread_id}).get("data")

    def like_thread(self, thread_id, like=True):
        return self.post("threads/setLike",
                         {"thread_id": thread_id, "is_like": like}).get("data")

    def check_can_create(self, category_id):
        return self.post("threads/checkCanCreate",
                         {"category_id": category_id}).get("data")

    def list_drafts(self, page_limit=20, page_offset=0):
        payload = self.get("threads/listMyDrafts",
                           params={"page_limit": page_limit,
                                   "page_offset": page_offset})
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

    def admin_thread(self, thread_id):
        return self.get("threads/getForAdmin", params={"id": thread_id}).get("data")

    # ---------------- posts / comments ----------------
    def list_posts(self, thread_id=None, user_id=None, page_limit=50,
                   page_offset=0, sort="-created_at", **extra):
        params = {"page_limit": page_limit, "page_offset": page_offset, "sort": sort}
        if thread_id is not None:
            params["thread_id"] = thread_id
        if user_id:
            params["user_id"] = user_id
        params.update(extra)
        payload = self.get("posts/list", params=params)
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

    def create_post(self, thread_id, content):
        """First level comment on a thread."""
        return self.post("posts/create",
                         {"thread_id": thread_id, "content": content}).get("data")

    def reply_comment(self, post_id, content, comment_post_id=None):
        """Nested reply to a comment."""
        body = {"post_id": post_id, "content": content}
        if comment_post_id:
            body["comment_post_id"] = comment_post_id
        return self.post("posts/createComment", body).get("data")

    def edit_post(self, post_id, content):
        return self.post("posts/%s" % post_id, {"content": content}).get("data")

    def delete_post(self, post_id):
        return self.request("DELETE", "posts/%s" % post_id).get("data")

    def batch_delete_posts(self, post_ids):
        return self.post("posts/batchDeletePosts",
                         {"ids": ",".join(str(p) for p in post_ids)}).get("data")

    def list_replies(self, post_id, page_limit=100, page_offset=0):
        payload = self.get("posts/listComments",
                           params={"post_id": post_id, "page_limit": page_limit,
                                   "page_offset": page_offset})
        data = payload.get("data")
        if isinstance(data, dict):
            return data.get("list") or []
        return data or []

    def like_post(self, post_id, like=True):
        return self.post("posts/setLike",
                         {"post_id": post_id, "is_like": like}).get("data")

    def sticky_post(self, post_id, is_sticky=True):
        return self.post("posts/setSticky",
                         {"post_id": post_id, "is_sticky": is_sticky}).get("data")

    def all_comments(self, thread_id, max_depth=6):
        """Depth-first flat list of every comment + nested reply."""
        out = []
        first, _ = self.list_posts(thread_id=thread_id, page_limit=100)
        stack = [p for p in first if not p.get("is_first")]
        while stack:
            c = stack.pop(0)
            c["_depth"] = 0
            out.append(c)
            self._collect_replies(c, out, 1, max_depth)
        return out

    def _collect_replies(self, parent, out, depth, max_depth):
        if depth > max_depth:
            return
        for r in self.list_replies(parent["id"]):
            r["_depth"] = depth
            r["_parent_id"] = parent["id"]
            out.append(r)
            self._collect_replies(r, out, depth + 1, max_depth)

    # ---------------- polls ----------------
    def polls_of_thread(self, thread_id):
        return self.get("polls/listByThread", params={"thread_id": thread_id}) \
                   .get("data") or []

    def vote_poll(self, poll_id, option_id):
        """option_id: int for single choice, list[int] for multi-choice polls."""
        return self.post("polls/vote",
                         {"poll_id": poll_id, "option_id": option_id}).get("data")

    def poll_voters(self, poll_id, option_id=None):
        params = {"poll_id": poll_id}
        if option_id is not None:
            params["option_id"] = option_id
        return self.get("polls/voters", params=params).get("data")

    # ---------------- resources / upload ----------------
    def upload_file(self, raw_bytes, file_name, mime="image/png"):
        payload = self.post(
            "resources",
            None,
            files={"file": (file_name, raw_bytes, mime)},
        )
        # fileName is sent as its own form field for API compatibility
        return payload.get("data")

    def upload_resource(self, raw_bytes, file_name, mime="image/png"):
        """multipart/form-data POST /bbs/resources with fileName + file fields."""
        url = self._resolve("resources")
        headers = self._auth_headers()
        files = {"fileName": (None, file_name), "file": (file_name, raw_bytes, mime)}
        try:
            resp = self.session.post(url, files=files, headers=headers,
                                     timeout=max(self.timeout, 60))
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise MBBSAPIError("upload failed: %s" % exc)
        if payload.get("success") is False:
            raise MBBSAPIError(str(payload.get("message") or "upload failed"),
                               payload=payload)
        return payload.get("data") or {}

    def delete_resource(self, file_path):
        return self.request("DELETE", "resources/%s" % file_path).get("data")

    @staticmethod
    def resource_url(file_path, base_url):
        """Static helper: absolute URL for an uploaded resource path."""
        base = base_url.rstrip("/")
        if not base.endswith("/bbs"):
            base += "/bbs"
        return base + RESOURCE_BASE + str(file_path).lstrip("/")

    def abs_resource_url(self, file_path):
        return self.api_base + RESOURCE_BASE + str(file_path).lstrip("/")

    def abs_resource_url(self, file_path):
        """Absolute first-party URL for an uploaded resource."""
        p = str(file_path)
        if p.startswith("http"):
            return p
        return self.api_base + RESOURCE_BASE + p.lstrip("/")

    # ---------------- messages ----------------
    def unread_count(self):
        return self.get("message/unreadMessageCount").get("data") or 0

    def list_messages(self, page_limit=20, page_offset=0):
        payload = self.get("message/listMessage",
                           params={"page_limit": page_limit,
                                   "page_offset": page_offset})
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

    def read_message(self, message_id):
        return self.get("message/readMessage",
                        params={"msg_id": message_id}).get("data")

    def mark_message_unread(self, message_id):
        return self.post("message/markMessageUnread",
                         {"msg_id": message_id}).get("data")

    def read_all_messages(self):
        return self.post("message/readAllMessage").get("data")

    def remove_message(self, message_id):
        return self.post("message/removeMessage", {"message_id": message_id}).get("data")

    # ---------------- series ----------------
    def list_series(self, user_id, page_limit=20, page_offset=0):
        payload = self.get("series", params={"user_id": user_id,
                                             "page_limit": page_limit,
                                             "page_offset": page_offset})
        return payload.get("data") or []

    def create_series(self, name, description=""):
        return self.post("series", {"name": name, "description": description}) \
                   .get("data")

    # ---------------- content cards ----------------
    def resolve_cards(self, thread_ids=(), user_ids=()):
        params = {}
        if thread_ids:
            params["thread_ids"] = ",".join(str(t) for t in thread_ids)
        if user_ids:
            params["user_ids"] = ",".join(str(u) for u in user_ids)
        return self.get("content-cards/resolve", params=params).get("data") or {}

    # ---------------- moderation ----------------
    def moderation_records(self, page_limit=20, page_offset=0, **filters):
        params = {"page_limit": page_limit, "page_offset": page_offset}
        params.update(filters)
        payload = self.get("moderation-records/list", params=params)
        return payload.get("data") or [], (payload.get("extra") or {}).get("totalCount")

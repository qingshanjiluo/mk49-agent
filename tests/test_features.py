import sys, pathlib, io, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import features
from features import load_all, content_safety
from mk49.agent import Agent

def test_registry_has_14():
    fl = load_all()
    assert len(fl) >= 14, "expected >=14 features, got %d" % len(fl)
    expected = {
        "smart_comment", "image_post", "url_card", "welcome_newcomer",
        "daily_digest", "poll_rider", "like_curator", "mention_watch",
        "command_center", "content_safety", "thread_summarizer",
        "hot_topic_tracker", "series_builder", "emoji_enhancer",
    }
    missing = expected - set(fl)
    assert not missing, "missing features: %s" % missing

def test_content_safety_regex():
    fl = load_all()
    cs = fl["content_safety"]

    class FakeAgent:
        class llm:
            @staticmethod
            def json(*a, **k):
                return {}
    ok, reason, _ = cs.check("今天天气真好", FakeAgent())
    assert ok, reason

    ok, reason, _ = cs.check("加微信 abc123 代理招募", FakeAgent())
    assert not ok

def test_plan_normalize():
    fl = load_all()

    class DummyState:
        def daily_count(self, k):
            return 0

    class DummyClient:
        user_id = 1

    class DummyObs:
        new_threads = [{"id": 1}]
        replyable = [{"id": 1, "_comments": [
            {"id": 9001, "_own": False, "_depth": 0}]}]
        thread_comments = {}
        mention_hits = []
        bot_threads = []
        unread = 0
        hot_titles = []

    class Dummy:
        state = DummyState(); client = DummyClient(); obs = DummyObs()
        nickname = "me"
        llm = None

    ag = Agent.__new__(Agent)
    ag.state, ag.client, ag.obs, ag.nickname = Dummy.state, Dummy.client, Dummy.obs, Dummy.nickname
    ag.cfg = {"daily_post_limit": 99, "target_categories": [2],
              "max_reply_depth": 3}
    plan = ag._normalize_plan({
        "reply_targets": [
            {"thread": 1, "post": 9001},
            {"thread": 999, "post": 0},      # not in replyable -> dropped
            {"thread": 1, "post": 9001},     # own-target dup -> still valid id
        ],
        "create_thread": True,
    })
    assert plan["reply_targets"][0] == {"thread": 1, "post": 9001}
    assert all(t["thread"] == 1 for t in plan["reply_targets"])
    assert plan["create_thread"] in (True, False)
    assert plan["thread_category"] == 2

def test_replyable_filters():
    from mk49.context import is_replyable
    cfg = {"skip_pinned": True, "skip_authors_below_id": 50}
    pinned = {"id": 1, "is_sticky": True, "user": {"id": 2000}}
    own = {"id": 2, "user": {"id": 1}}
    veteran = {"id": 3, "user": {"id": 12}}
    normal = {"id": 4, "user": {"id": 2000}}
    my_id = 1
    assert is_replyable(pinned, cfg, my_id)[0] is False
    assert is_replyable(own, cfg, my_id)[0] is False
    assert is_replyable(veteran, cfg, my_id)[0] is False
    assert is_replyable(normal, cfg, my_id)[0] is True

def test_emoji_enhancer_uses_shortcodes():
    fl = load_all()

    class FakeAgent:
        class state:
            data = {"emoji_pool": ["miao", "aww"]}

    import random
    random.seed(0)
    out = fl["emoji_enhancer"].enhance("hello", FakeAgent(), chance=1.0)
    assert out.startswith("hello ")
    assert ":miao:" in out or ":aww:" in out

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed += 1
        except Exception:
            import traceback; traceback.print_exc(); print("FAIL", f.__name__)
    print("%d/%d feature tests passed" % (passed, len(fns)))
    sys.exit(0 if passed == len(fns) else 1)

import sys, pathlib, io
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from mbbs import render


def test_normalize_blank_lines():
    out = render.normalize("## 标题\n正文一行\n- a\n- b")
    assert "## 标题\n\n正文一行" in out
    assert "\n\n- a" in out


def test_auto_code_commands():
    text = "先跑这个：\n$ python run.py doctor\n$ pip install -r requirements.txt\n然后看输出"
    out = render.auto_code(text)
    assert "```\n$ python run.py doctor" in out
    assert out.count("```") >= 2


def test_auto_code_skips_when_fenced():
    text = "```\n$ python run.py\n```"
    assert render.auto_code(text) == text


def test_auto_code_prose_untouched():
    text = "我觉得驱逐前期更灵活\n巡洋容错高一点"
    assert "```" not in render.auto_code(text)


def test_auto_link_wraps():
    out = render.auto_link("见 https://forum.mk49.top/x 页面")
    assert "[forum.mk49.top/x](https://forum.mk49.top/x)" in out


def test_cards_capped_at_10():
    base = "正文"
    cards = [render.thread_card(100 + i) for i in range(15)]
    out = render.inject_cards(base, cards)
    assert render.count_cards(out) == 10


def test_pretty_comment_has_quote_and_body():
    out = render.pretty_comment("同意这个说法", parent_text="我觉得驱逐强")
    assert out.startswith("> ")
    assert "同意这个说法" in out


def test_pretty_post_layout():
    out = render.pretty_post(title="测试", body="正文", image_url="https://x/y.png",
                              cards=[render.thread_card(48248)], footer="自动")
    assert "## 测试" in out
    assert "![配图](https://x/y.png)" in out
    assert "[threadcard:48248]" in out
    assert out.rstrip().endswith("*自动*")


def test_shorten_closes_fences():
    text = "```python\n" + ("x = 1\n" * 900) + "```"
    out = render.shorten_comment_md(text, 200)
    assert out.count("```") % 2 == 0


def test_beautify_idempotent_ish():
    a = render.beautify("## T\n\n正文\n\n- x\n- y")
    b = render.beautify(a)
    assert a.strip() == b.strip()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed += 1
        except Exception:
            import traceback; traceback.print_exc(); print("FAIL", f.__name__)
    print("%d/%d render tests passed" % (passed, len(fns)))
    sys.exit(0 if passed == len(fns) else 1)

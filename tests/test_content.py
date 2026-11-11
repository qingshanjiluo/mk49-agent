import sys, pathlib, io, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from mbbs.content import (strip_html, extract_image_urls, thread_card,
                           user_card, poll_placeholder, inline_image,
                           truncate, quote_block, code_block, has_custom_emoji,
                           extract_urls)

def test_strip_html():
    assert strip_html("<p>hello <b>world</b></p>") == "hello world"
    assert strip_html("a<br/>b") == "a\nb"
    assert strip_html("") == ""
    assert "<" not in strip_html("<script>x=1</script>ok")

def test_cards():
    assert thread_card(48248) == "[threadcard:48248]"
    assert user_card(1501) == "[usercard:1501]"
    assert "mbbs-poll:" in poll_placeholder("abc123")

def test_inline_image():
    s = inline_image("https://x/y.png", "alt")
    assert s == "![alt](https://x/y.png)"
    assert inline_image("") == ""

def test_extract_urls():
    urls = extract_urls("see https://a.com/x and http://b.org/y")
    assert len(urls) == 2

def test_extract_images():
    h = '<img src="https://a/b.png"><img src="/local/c.png">'
    assert extract_image_urls(h) == ["https://a/b.png"]

def test_truncate():
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 10) == "abc"

def test_quote_and_code():
    assert quote_block("a\nb") == "> a\n> b"
    assert code_block("x", "py").startswith("```py")

def test_emoji():
    assert has_custom_emoji("hi :miao:")

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed += 1
        except AssertionError:
            import traceback; traceback.print_exc(); print("FAIL", f.__name__)
    print("%d/%d content tests passed" % (passed, len(fns)))
    sys.exit(0 if passed == len(fns) else 1)

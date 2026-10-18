"""Structural checks on The Office's index.html: balanced tags and unique ids (a duplicated header block once
left a stuck "connecting..." pill and closed the header early)."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "template" / "office" / "index.html"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Nesting(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            self.errors.append((tag, self.getpos()))


class OfficeHtmlTest(unittest.TestCase):
    def test_tags_balanced(self):
        p = _Nesting()
        p.feed(HTML.read_text(encoding="utf-8"))
        self.assertEqual(p.errors, [], "unexpected closing tags")
        self.assertEqual(p.stack, [], "unclosed tags")

    def test_ids_unique(self):
        ids = re.findall(r'\bid="([^"]+)"', HTML.read_text(encoding="utf-8"))
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [], f"duplicate ids: {dupes}")


if __name__ == "__main__":
    unittest.main()

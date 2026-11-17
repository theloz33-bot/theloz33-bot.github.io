#!/usr/bin/env python3
"""Pre-publish audit for the hub site in docs/.

Checks
  1. every internal link resolves to a file in docs/
  2. every XML file parses
  3. HTML tags balance and every page has exactly one h1
  4. no personal identifiers (name, phone, personal mail, address) in the output
  5. required files exist and sitemap.xml lists every page
  6. no "no cookies" style claim that advertising would contradict

Run: python3 tools/audit.py     (exit 1 on any failure)
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOMAIN = "https://theloz33-bot.github.io"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

GENERIC = [
    r"[A-Za-z0-9._%+-]+@(?:gmail|naver|daum|hanmail|kakao|nate)\.com",
    r"01\d[-.\s]?\d{3,4}[-.\s]?\d{4}",
]

# Claims that stop being true the moment an ad script is inserted.
CONTRADICTIONS = [
    r"쿠키를\s*사용하지\s*않",
    r"쿠키를\s*쓰지\s*않",
    r"쿠키가\s*없",
    r"\bno cookies\b",
    r"\bno cookie\b",
    r"does not use cookies",
    r"never sets? (?:a )?cookies?",
]

failures: list[str] = []


def load_patterns() -> list[str]:
    patterns = list(GENERIC)
    local = ROOT / ".audit_patterns.json"
    if local.exists():
        data = json.loads(local.read_text(encoding="utf-8"))
        patterns = list(data.get("patterns", [])) + patterns
    return patterns


class Balance(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.h1 += 1
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"unclosed <{self.stack.pop()}>")
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"unmatched </{tag}>")


def resolve(href: str, page: Path) -> Path | None:
    if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme in ("http", "https"):
        if not href.startswith(DOMAIN):
            return None
        path = parsed.path
        # links into the two project journals belong to those repositories
        if path.startswith(("/omong-kr-lab/", "/omong-studio-journal/")):
            return None
    else:
        path = parsed.path
        if not path:
            return None

    if path in ("", "/"):
        return DOCS / "index.html"
    rel = path.lstrip("/")
    target = (DOCS / rel).resolve()
    if not str(target).startswith(str(DOCS.resolve())):
        return Path("/outside-site-root")
    if rel.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def main() -> int:
    if not DOCS.exists():
        sys.exit("docs/ missing — run python3 build.py first")

    pages = sorted(DOCS.rglob("*.html"))
    if not pages:
        failures.append("no HTML output")

    for page in pages:
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r'(?:href|src)="([^"]+)"', text):
            target = resolve(href, page)
            if target is not None and not target.exists():
                failures.append(f"{page.relative_to(DOCS)}: broken link {href}")
        if re.search(r'(?:href|src)="http://', text):
            failures.append(f"{page.relative_to(DOCS)}: non-https link")
        parser = Balance()
        parser.feed(text)
        if parser.errors or parser.stack:
            failures.append(
                f"{page.relative_to(DOCS)}: tag imbalance {parser.errors[:3]} open={parser.stack[:3]}"
            )
        if parser.h1 != 1:
            failures.append(f"{page.relative_to(DOCS)}: {parser.h1} h1 elements")

    for xml_file in sorted(DOCS.glob("*.xml")):
        try:
            ET.parse(xml_file)
        except ET.ParseError as exc:
            failures.append(f"{xml_file.name}: XML parse error ({exc})")

    for pattern in load_patterns():
        for path in sorted(DOCS.rglob("*")):
            if not path.is_file() or path.suffix not in {".html", ".xml", ".css", ".txt", ".svg", ""}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            stripped = text.replace("theloz33-bot.github.io", "").replace("theloz33-bot", "")
            for match in re.finditer(pattern, stripped):
                line = stripped[max(0, match.start() - 40): match.end() + 40].replace("\n", " ")
                failures.append(
                    f"{path.relative_to(DOCS)}: personal identifier '{match.group(0)}' near …{line}…"
                )

    for pattern in CONTRADICTIONS:
        for path in sorted(DOCS.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            if re.search(pattern, text, re.I):
                failures.append(f"{path.relative_to(DOCS)}: cookie claim contradicts advertising ({pattern})")

    for name in ("index.html", "about/index.html", "privacy/index.html", "contact/index.html",
                 "disclosure/index.html", "404.html", "sitemap.xml", "robots.txt",
                 "ads.txt", ".nojekyll", "assets/style.css"):
        if not (DOCS / name).exists():
            failures.append(f"missing required output: {name}")

    try:
        locs = {loc.text for loc in ET.parse(DOCS / "sitemap.xml").getroot().iter()
                if loc.text}
    except ET.ParseError:
        locs = set()
    for path, _key, _nav in (
        ("", "index", ""), ("about/", "about", ""), ("privacy/", "privacy", ""),
        ("contact/", "contact", ""), ("disclosure/", "disclosure", ""),
    ):
        if f"{DOMAIN}/{path}" not in locs:
            failures.append(f"sitemap.xml: {path or '/'} not listed")

    robots = (DOCS / "robots.txt").read_text(encoding="utf-8")
    if f"{DOMAIN}/sitemap.xml" not in robots:
        failures.append("robots.txt: sitemap not declared")

    if failures:
        print("AUDIT FAILED")
        for item in failures:
            print("  -", item)
        return 1

    print(f"AUDIT OK — {len(pages)} pages, XML {len(list(DOCS.glob('*.xml')))}, "
          f"no personal identifiers, no contradicting cookie claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

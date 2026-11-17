#!/usr/bin/env python3
"""Omong Studio hub — static site builder.

Python 3 standard library only. No external CDN, font or framework.

    python3 build.py            # render docs/ from templates/pages + data/
    python3 build.py --sync     # refresh data/feed.json from the two sibling journals
    python3 build.py --check    # build, then fail if any page is thin or a page is missing

Inputs
    data/site.json          brand, base URL, the two journals, adsense_client slot
    data/feed.json          curated latest posts for both journals (written by --sync)
    templates/base.html     page shell with {{placeholder}} slots
    templates/pages/*.html  one fragment per page, Korean and English on the same page
    static/                 copied to docs/assets/
    ads.txt                 copied to docs/ads.txt unchanged
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # src/ — the sources
SITE = ROOT.parent                              # repository root — published as-is
DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"
PAGES = TEMPLATES / "pages"
STATIC = ROOT / "static"
OUT = SITE
KST = timezone(timedelta(hours=9))

# path (relative to docs/) -> fragment name -> nav key
PAGE_LIST = [
    ("", "index", "home"),
    ("about/", "about", "about"),
    ("privacy/", "privacy", "privacy"),
    ("contact/", "contact", "contact"),
    ("disclosure/", "disclosure", "disclosure"),
]

# Journals checked out next to this repo; --sync reads their post front matter.
SIBLINGS = {
    "kr": SITE.parent / "blog-omong-kr",
    "en": SITE.parent / "blog-omong-studio",
}


# ---------------------------------------------------------------- helpers


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def render(template: str, values: dict) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    leftovers = re.findall(r"\{\{([a-z_]+)\}\}", out)
    if leftovers:
        raise SystemExit(f"unfilled template placeholder: {sorted(set(leftovers))}")
    return out


def esc(value: str) -> str:
    return html.escape(str(value), quote=False)


def tracked_files(repo: Path, subdir: str) -> set[str] | None:
    """Files git knows about under repo/subdir, or None when git or the repo is unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", subdir],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def parse_front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    lines = text.split("\n")
    meta: dict = {}
    for line in lines[1:]:
        if line.strip() in ("---", "..."):
            break
        if not line.strip() or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = value.strip("\"'")
    return meta


def fmt_date(value: str, lang: str) -> str:
    try:
        date = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    if lang == "ko":
        return f"{date.year}년 {date.month}월 {date.day}일"
    return f"{date.strftime('%b')} {date.day}, {date.year}"


# ---------------------------------------------------------------- feed


def sync_feed() -> dict:
    """Read both journal repositories and write data/feed.json."""
    site = load_json(DATA / "site.json")
    feed = {"updated": datetime.now(KST).strftime("%Y-%m-%d"), "journals": {}}
    for key, path in SIBLINGS.items():
        posts_dir = path / "posts"
        if not posts_dir.is_dir():
            print(f"  skip {key}: {posts_dir} not found (keep the existing feed.json entry)")
            previous = load_json(DATA / "feed.json")["journals"].get(key, {})
            if previous:
                feed["journals"][key] = previous
            continue
        posts = []
        # A post counts as published once its file is committed in the journal repository —
        # that commit is what Pages deploys. A working copy written but not yet committed
        # would otherwise become a dead link from this hub.
        committed = tracked_files(path, "posts")
        for md in sorted(posts_dir.glob("*.md")):
            if md.name.startswith("_"):
                continue
            meta = parse_front_matter(md.read_text(encoding="utf-8"))
            if not meta.get("slug") or not meta.get("title"):
                continue
            if committed is not None and f"posts/{md.name}" not in committed:
                print(f"  skip uncommitted {key}: {md.name}")
                continue
            posts.append(
                {
                    "title": meta["title"],
                    "url": f"{site['journals'][key]['url']}posts/{meta['slug']}/",
                    "date": meta.get("date", ""),
                    "category": meta.get("category", ""),
                    "excerpt": meta.get("excerpt") or meta.get("description", ""),
                }
            )
        site_local = load_json(path / "data" / "site.json")
        labels = {c["key"]: c["label"] for c in site_local.get("categories", [])}
        for post in posts:
            post["category"] = labels.get(post["category"], post["category"])
        posts.sort(key=lambda p: p["date"], reverse=True)
        journal = dict(site["journals"][key])
        journal["posts"] = posts
        journal["count"] = len(posts)
        if key == "kr":
            journal["categories"] = [c["label"] for c in site_local.get("categories", [])]
        else:
            seen: list[str] = []
            for post in posts:
                if post["category"] and post["category"] not in seen:
                    seen.append(post["category"])
            journal["categories"] = seen
        feed["journals"][key] = journal
        print(f"  {key}: {len(posts)} posts from {path.name}")
    DATA.mkdir(exist_ok=True)
    (DATA / "feed.json").write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return feed


# ---------------------------------------------------------------- blocks


def post_list(posts: list[dict], lang: str, limit: int = 6) -> str:
    rows = []
    for post in posts[:limit]:
        rows.append(
            f"""<li>
  <a href="{post['url']}">
    <span class="post-cat">{esc(post['category'])}</span>
    <span class="post-title">{esc(post['title'])}</span>
    <span class="post-meta">{esc(fmt_date(post['date'], lang))}</span>
  </a>
</li>"""
        )
    return "\n".join(rows)


def category_pills(categories: list[str]) -> str:
    return "".join(f'<span class="pill">{esc(c)}</span>' for c in categories)


def start_here(posts: list[dict], lang: str, picks: list[str]) -> str:
    by_url = {p["url"]: p for p in posts}
    rows = []
    for url in picks:
        post = by_url.get(url)
        if not post:
            continue
        rows.append(
            f"""<li>
  <a href="{post['url']}">
    <span class="post-title">{esc(post['title'])}</span>
    <span class="post-excerpt">{esc(post['excerpt'])}</span>
  </a>
</li>"""
        )
    if not rows:
        rows = [post_list(posts, lang, 3)]
    return "\n".join(rows)


def sitemap(site: dict, pages: list[tuple[str, str]], lastmod: str) -> str:
    base = site["base_url"].rstrip("/")
    body = "".join(
        f"  <url><loc>{base}/{path}</loc><lastmod>{lastmod}</lastmod>"
        f"<changefreq>{'weekly' if path == '' else 'monthly'}</changefreq></url>\n"
        for path, _ in pages
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}</urlset>\n"
    )


# ---------------------------------------------------------------- build


def build() -> int:
    site = load_json(DATA / "site.json")
    feed_path = DATA / "feed.json"
    if not feed_path.exists():
        raise SystemExit("data/feed.json missing — run python3 build.py --sync first")
    feed = load_json(feed_path)
    journals = feed["journals"]
    base_html = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    year = datetime.now(KST).year
    updated = feed.get("updated", datetime.now(KST).strftime("%Y-%m-%d"))

    # GitHub Pages serves the repository root, so the sources sit in src/ and only the
    # generated outputs are replaced here — never the directory itself.
    for stale in ("index.html", "404.html", "sitemap.xml", "robots.txt", "ads.txt",
                  ".nojekyll", "assets", "about", "privacy", "contact", "disclosure"):
        target = OUT / stale
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    client = (site.get("adsense_client") or "").strip()
    if client:
        if not re.fullmatch(r"ca-pub-\d{16}", client):
            raise SystemExit(f"adsense_client looks wrong: {client!r} (expected ca-pub-XXXXXXXXXXXXXXXX)")
        adsense = (
            f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client}" '
            'crossorigin="anonymous"></script>'
        )
    else:
        adsense = ""

    kr = journals.get("kr", {})
    en = journals.get("en", {})
    kr_posts = kr.get("posts", [])
    en_posts = en.get("posts", [])

    start_picks_kr = [
        f"{kr.get('url', '')}posts/brand-video-longform-or-shortform-first/",
        f"{kr.get('url', '')}posts/smartphone-light-and-mic-setup/",
    ]
    start_picks_en = [
        f"{en.get('url', '')}posts/consistent-ai-characters-9-16-short-form/",
        f"{en.get('url', '')}posts/cinematic-ai-music-video-pipeline/",
    ]

    nav = {
        "about": "/about/",
        "privacy": "/privacy/",
        "contact": "/contact/",
        "disclosure": "/disclosure/",
        "kr": kr.get("url", "https://theloz33-bot.github.io/omong-kr-lab/"),
        "en": en.get("url", "https://theloz33-bot.github.io/omong-studio-journal/"),
    }

    page_meta = {
        "index": (
            f"{site['brand']} — AI short-form, music videos, and the notes behind them",
            site["description"],
        ),
        "about": (
            f"스튜디오 소개 · About {site['brand']}",
            "오몽 스튜디오가 무엇을 만들고, 어떤 기준으로 쓰고 발행하는지. What the studio makes, publishes, and will not publish.",
        ),
        "privacy": (
            f"개인정보처리방침 · Privacy Policy · {site['brand']}",
            "이 사이트가 직접 수집하는 정보, Google AdSense와 제3자 광고 쿠키, 맞춤형 광고 수신 거부 방법을 한국어와 영어로 안내합니다.",
        ),
        "contact": (
            f"문의하기 · Contact {site['brand']}",
            "제작 의뢰, 구매 문의, 정정 요청 창구를 안내합니다. Where to write about commissions, orders and corrections.",
        ),
        "disclosure": (
            f"제휴·광고 고지 · Disclosure · {site['brand']}",
            "제휴 링크와 광고 게재, 제작 의뢰의 대가 관계를 밝힙니다. How affiliate links, advertising and commissions are handled.",
        ),
    }

    def structured_data(key: str, title: str, description: str, canonical: str) -> str:
        """One JSON-LD block per page; the home page also declares the two journals."""
        if key == "index":
            data = {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "Organization",
                        "@id": f"{site['base_url'].rstrip('/')}/#studio",
                        "name": site["brand"],
                        "alternateName": site["brand_ko"],
                        "url": f"{site['base_url'].rstrip('/')}/",
                        "description": site["description"],
                        "sameAs": [
                            kr.get("url", ""),
                            en.get("url", ""),
                            "https://lozzy36.gumroad.com/",
                        ],
                    },
                    {
                        "@type": "WebSite",
                        "@id": f"{site['base_url'].rstrip('/')}/#site",
                        "name": site["brand"],
                        "url": f"{site['base_url'].rstrip('/')}/",
                        "inLanguage": ["ko-KR", "en"],
                        "publisher": {"@id": f"{site['base_url'].rstrip('/')}/#studio"},
                    },
                ],
            }
        else:
            data = {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical,
                "inLanguage": site["language"],
                "isPartOf": {"@id": f"{site['base_url'].rstrip('/')}/#site"},
            }
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"

    def page_block(key: str, title: str, description: str, path: str) -> str:
        fragment = (PAGES / f"{key}.html").read_text(encoding="utf-8")
        content = render(
            fragment,
            {
                "kr_latest": post_list(kr_posts, "ko", 6),
                "en_latest": post_list(en_posts, "en", 6),
                "kr_categories": category_pills(kr.get("categories", [])),
                "en_categories": category_pills(en.get("categories", [])),
                "kr_start": start_here(kr_posts, "ko", start_picks_kr),
                "en_start": start_here(en_posts, "en", start_picks_en),
                "kr_url": kr.get("url", ""),
                "en_url": en.get("url", ""),
                "kr_rss": kr.get("rss", ""),
                "en_rss": en.get("rss", ""),
                "kr_name": esc(kr.get("name", "")),
                "en_name": esc(en.get("name", "")),
                "kr_blurb": esc(kr.get("blurb", "")),
                "en_blurb": esc(en.get("blurb", "")),
                "kr_blurb_en": esc(kr.get("blurb_en", "")),
                "en_blurb_ko": esc(en.get("blurb_ko", "")),
                "kr_count": str(kr.get("count", len(kr_posts))),
                "en_count": str(en.get("count", len(en_posts))),
                "updated": esc(fmt_date(updated, "ko")),
            },
        )
        canonical = f"{site['base_url'].rstrip('/')}/{path}"
        return render(
            base_html,
            {
                "lang": site["language"],
                "locale": site["locale"],
                "brand": site["brand"],
                "brand_ko": site["brand_ko"],
                "tagline": html.escape(site["tagline"], quote=True),
                "title": html.escape(title, quote=True),
                "description": html.escape(description, quote=True),
                "canonical": canonical,
                "base": "/",
                "nav": nav_html(key),
                "content": content,
                "year": year,
                "jsonld": structured_data(key, title, description, canonical),
                "adsense": adsense,
            },
        )

    for path, key, navkey in PAGE_LIST:
        title, description = page_meta[key]
        target = OUT / path / "index.html" if path else OUT / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page_block(key, title, description, path), encoding="utf-8")

    # 404
    notfound = render(
        (PAGES / "404.html").read_text(encoding="utf-8"), {"kr_url": kr.get("url", "")}
    )
    (OUT / "404.html").write_text(
        render(
            base_html,
            {
                "lang": site["language"],
                "locale": site["locale"],
                "brand": site["brand"],
                "brand_ko": site["brand_ko"],
                "tagline": html.escape(site["tagline"], quote=True),
                "title": f"페이지를 찾을 수 없습니다 · Page not found · {site['brand']}",
                "description": "주소가 바뀌었거나 없는 페이지입니다.",
                "canonical": f"{site['base_url'].rstrip('/')}/404.html",
                "base": "/",
                "nav": nav_html(""),
                "content": notfound,
                "year": year,
                "jsonld": "",
                "adsense": adsense,
            },
        ),
        encoding="utf-8",
    )

    # feed files
    pages_for_map = [(path, key) for path, key, _ in PAGE_LIST]
    (OUT / "sitemap.xml").write_text(sitemap(site, pages_for_map, updated), encoding="utf-8")
    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        f"Sitemap: {site['base_url'].rstrip('/')}/sitemap.xml\n", encoding="utf-8"
    )

    # ads.txt is kept at the repo root so it can be edited without touching build.py
    ads_txt = ROOT / "ads.txt"
    if ads_txt.exists():
        shutil.copy2(ads_txt, OUT / "ads.txt")
    else:
        print("  warning: ads.txt missing at repo root")

    for path in STATIC.rglob("*"):
        if path.is_file():
            target = OUT / "assets" / path.relative_to(STATIC)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    print(f"built {len(PAGE_LIST) + 1} pages -> {OUT}")
    print(f"  adsense_client: {'set' if client else 'empty (no script emitted)'}")
    print(f"  feed: {len(kr_posts)} KR posts, {len(en_posts)} EN posts (updated {updated})")

    if "--check" in sys.argv:
        problems = []
        for name in ("index.html", "about/index.html", "privacy/index.html",
                     "contact/index.html", "disclosure/index.html", "404.html",
                     "sitemap.xml", "robots.txt", "ads.txt", ".nojekyll"):
            if not (OUT / name).exists():
                problems.append(f"missing {name}")
        for page in OUT.rglob("*.html"):
            if page.name == "404.html" or {".git", "src"} & set(page.relative_to(OUT).parts):
                continue
            text = page.read_text(encoding="utf-8")
            words = len(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", re.sub(r"<[^>]+>", " ", text)))
            if words < 220:
                problems.append(f"{page.relative_to(OUT)}: only {words} words")
        if not kr_posts or not en_posts:
            problems.append("feed.json has an empty journal")
        if problems:
            raise SystemExit("build --check failed:\n  - " + "\n  - ".join(problems))
        print("  --check OK")
    return 0


def nav_html(current: str) -> str:
    items = [
        ("about", "/about/", "스튜디오"),
        ("kr", "https://theloz33-bot.github.io/omong-kr-lab/", "한국어 저널"),
        ("en", "https://theloz33-bot.github.io/omong-studio-journal/", "English journal"),
        ("contact", "/contact/", "문의"),
    ]
    links = []
    for key, href, label in items:
        active = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{href}"{active}>{esc(label)}</a>')
    return "".join(links)


if __name__ == "__main__":
    if "--sync" in sys.argv:
        sync_feed()
    raise SystemExit(build())

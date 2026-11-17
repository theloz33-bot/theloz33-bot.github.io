# theloz33-bot.github.io — Omong Studio hub

The root domain of Omong Studio: one page that introduces the studio, curates both journals, and
carries the pages an advertising review looks for — About, Privacy Policy, Contact and Disclosure.

Live: <https://theloz33-bot.github.io/>

## What is here

| Path | What it is |
| --- | --- |
| `/` | Studio hub: what the studio makes, both journals with their latest posts, reading paths, topic table |
| `/about/` | Who writes this, what gets published, the three editorial rules, how the site earns |
| `/privacy/` | Privacy policy — host logs, Google AdSense / DoubleClick cookies, opt-out links (ko + en) |
| `/contact/` | Commission, purchase and correction channels. No personal email, phone or address |
| `/disclosure/` | Affiliate links, advertising, commissions, editorial independence |
| `/ads.txt` | Comment-only stub until AdSense issues the publisher ID |

Both journals live in their own repositories and are served under this domain:

- Korean journal — <https://theloz33-bot.github.io/omong-kr-lab/>
- English journal — <https://theloz33-bot.github.io/omong-studio-journal/>

## Build

```bash
python3 src/build.py --sync   # read posts/*.md from the two sibling repos into src/data/feed.json
python3 src/build.py --check  # render the site and fail if a page is missing or thin
python3 src/tools/audit.py    # links, XML, tag balance, h1 count, personal-info scan
./deploy.sh "message"         # all three, then commit and push
```

GitHub Pages serves `main` → the repository root, so the generated pages (`index.html`, `about/`,
`privacy/`, `contact/`, `disclosure/`, `assets/`, `sitemap.xml`, `robots.txt`, `ads.txt`) sit next to
`src/`, which holds the builder and its inputs. No dependencies beyond Python 3.

`--sync` expects `blog-omong-kr/` and `blog-omong-studio/` next to this folder. Without them the
build uses the committed `src/data/feed.json`, so the site still builds from a fresh clone.

## Turning on AdSense

1. `src/data/site.json` → `"adsense_client": "ca-pub-XXXXXXXXXXXXXXXX"`.
2. Rebuild: the `<head>` of every page gets the `adsbygoogle.js` script; an empty value emits
   nothing.
3. `ads.txt` → uncomment the `google.com, pub-…, DIRECT, f08c47fec0942fa0` line with the same
   publisher number.
4. Push and confirm `/ads.txt` is served at the domain root — AdSense only reads ads.txt from the
   root, so this one file covers both journals.

## Rules for this repository

- No real name, personal email, phone number or address in any page. `src/tools/audit.py` scans the
  built output against `.audit_patterns.json`, which is gitignored on purpose.
- Never write that the site sets no cookies: advertising may set them. The privacy policy says what
  actually happens.
- Every page ships Korean content first and an English section under it, because the two journals
  it links to are in different languages.

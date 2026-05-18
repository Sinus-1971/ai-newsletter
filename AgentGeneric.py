#!/usr/bin/env python3
"""
AgentGeneric — Subject-based newsletter generator.
Asks for a subject, fetches articles from multiple sources, generates an
AI editorial summary via Claude API, and produces a styled HTML newsletter.
Optionally schedules daily runs via cron.

Setup:
  export GMAIL_APP_PASSWORD="your-app-password-here"
  export ANTHROPIC_API_KEY="your-anthropic-api-key"
"""

import feedparser
import requests
import anthropic
from dotenv import load_dotenv
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote_plus
import json
import re
import time
import smtplib
import os
import sys
import subprocess
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

EMAIL_FROM = "sinankezer@gmail.com"
EMAIL_TO = "sinankezer@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MAX_ARTICLES_PER_SOURCE = 5

AUDIO_OPTIONS = {
    "0": {"name": "No audio",  "voice": None,       "lang_name": None,      "code": "0"},
    "1": {"name": "English",   "voice": "Samantha",  "lang_name": "English", "code": "1"},
    "2": {"name": "Turkish",   "voice": "Yelda",     "lang_name": "Turkish", "code": "2"},
    "3": {"name": "French",    "voice": "Thomas",    "lang_name": "French",  "code": "3"},
}

AUDIO_SPEED = 1.0

SPEED_OPTIONS = {
    "1": 0.75,
    "2": 1.0,
    "3": 1.25,
}

RSS_PATTERNS = ["/feed/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/feeds/posts/default"]


def discover_best_sites(subject):
    """Use Claude API to find the 10 best websites for a given subject."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARNING] ANTHROPIC_API_KEY not set — using fallback sources.")
        return None

    prompt = f"""For the subject "{subject}", list the 10 best and most authoritative websites
that regularly publish news, analysis, or research about this topic.

Return ONLY a JSON array of objects with these fields:
- "name": short display name of the site
- "domain": the domain name (e.g., "techcrunch.com")
- "rss_url": the RSS/Atom feed URL if you know it, otherwise null
- "site_url": the main URL for the relevant section of the site

Example format:
[
  {{"name": "TechCrunch", "domain": "techcrunch.com", "rss_url": "https://techcrunch.com/feed/", "site_url": "https://techcrunch.com/"}},
  {{"name": "MIT Tech Review", "domain": "technologyreview.com", "rss_url": null, "site_url": "https://www.technologyreview.com/"}}
]

Return ONLY the JSON array, no other text."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            sites = json.loads(match.group())
            print(f"Discovered {len(sites)} best sites for '{subject}'")
            return sites
    except Exception as e:
        print(f"[WARNING] Site discovery failed: {e}")

    return None


def try_rss_url(url):
    """Check if an RSS URL is reachable and returns a valid feed."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            feed = feedparser.parse(resp.content)
            if feed.entries:
                return True
    except Exception:
        pass
    return False


def discover_rss_for_site(domain):
    """Try common RSS URL patterns for a domain."""
    base = f"https://{domain}"
    for pattern in RSS_PATTERNS:
        url = base.rstrip("/") + pattern
        if try_rss_url(url):
            return url
    base_www = f"https://www.{domain}"
    for pattern in RSS_PATTERNS:
        url = base_www.rstrip("/") + pattern
        if try_rss_url(url):
            return url
    return None


def build_sources(subject, discovered_sites=None):
    """Build RSS sources from discovered sites, with Google News fallbacks."""
    encoded = quote_plus(subject)
    sources = []

    if discovered_sites:
        print()
        print("Resolving RSS feeds for discovered sites...")
        for site in discovered_sites[:10]:
            name = site.get("name", site.get("domain", "Unknown"))
            domain = site.get("domain", "")
            rss_url = site.get("rss_url")
            site_url = site.get("site_url", f"https://{domain}")

            # Try the AI-suggested RSS URL first
            if rss_url and try_rss_url(rss_url):
                print(f"  {name}: direct RSS found")
                sources.append({
                    "name": name,
                    "url": rss_url,
                    "site_url": site_url,
                })
                continue

            # Try common RSS patterns
            found_rss = discover_rss_for_site(domain)
            if found_rss:
                print(f"  {name}: RSS discovered at {found_rss}")
                sources.append({
                    "name": name,
                    "url": found_rss,
                    "site_url": site_url,
                    "filter_keywords": [kw.lower() for kw in subject.split()],
                })
                continue

            # Fall back to Google News filtered to this site
            print(f"  {name}: no RSS — using Google News site filter")
            sources.append({
                "name": name,
                "url": f"https://news.google.com/rss/search?q={encoded}+site:{domain}&hl=en&gl=US&ceid=US:en",
                "site_url": site_url,
            })

    # Always add Google News general + recent and Reddit as supplementary sources
    sources.extend([
        {
            "name": f"Google News — {subject}",
            "url": f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en",
            "site_url": f"https://news.google.com/search?q={encoded}",
        },
        {
            "name": f"Google News — {subject} (recent)",
            "url": f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en&gl=US&ceid=US:en",
            "site_url": f"https://news.google.com/search?q={encoded}",
        },
        {
            "name": f"Reddit — {subject}",
            "url": f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit=10&t=week",
            "site_url": f"https://www.reddit.com/search/?q={encoded}",
            "type": "reddit",
        },
    ])

    return sources


def strip_html(text):
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def truncate(text, max_len=250):
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def parse_date(entry):
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None) or entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def matches_keywords(entry, keywords):
    text = (
        (entry.get("title", "") + " " + strip_html(entry.get("summary", "")))
        .lower()
    )
    return any(kw in text for kw in keywords)


def fetch_reddit(source):
    articles = []
    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        for child in data.get("data", {}).get("children", [])[:MAX_ARTICLES_PER_SOURCE]:
            post = child.get("data", {})
            title = post.get("title", "No Title")
            link = post.get("url", "")
            if link.startswith("/r/"):
                link = f"https://www.reddit.com{link}"
            summary = truncate(strip_html(post.get("selftext", "")))
            created = post.get("created_utc")
            pub_date = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            date_str = pub_date.strftime("%b %d, %Y") if pub_date else ""
            articles.append({
                "title": title,
                "link": link,
                "summary": summary or "Reddit discussion",
                "date": date_str,
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
            })
    except Exception as e:
        print(f"  [WARNING] Failed to fetch {source['name']}: {e}")
    return articles


def fetch_rss(source):
    articles = []
    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        keywords = source.get("filter_keywords")

        for entry in feed.entries[:20]:
            if keywords and not matches_keywords(entry, keywords):
                continue

            title = entry.get("title", "No Title")
            link = entry.get("link", "")
            summary = truncate(strip_html(entry.get("summary", "")))
            pub_date = parse_date(entry)
            date_str = pub_date.strftime("%b %d, %Y") if pub_date else ""

            articles.append({
                "title": title,
                "link": link,
                "summary": summary,
                "date": date_str,
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
            })

            if len(articles) >= MAX_ARTICLES_PER_SOURCE:
                break

    except Exception as e:
        print(f"  [WARNING] Failed to fetch {source['name']}: {e}")

    return articles


CACHE_DIR = os.path.join(SCRIPT_DIR, ".source_cache")
CACHE_MAX_AGE_DAYS = 7


def get_cache_path(subject):
    safe = sanitize_filename(subject)
    return os.path.join(CACHE_DIR, f"{safe}_sources.json")


def load_cached_sources(subject):
    path = get_cache_path(subject)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            cache = json.load(f)
        cached_date = datetime.strptime(cache["date"], "%Y-%m-%d")
        age = (datetime.now() - cached_date).days
        if age >= CACHE_MAX_AGE_DAYS:
            print(f"Source cache expired ({age} days old) — rediscovering...")
            return None
        print(f"Using cached sources ({age} day(s) old, refreshes weekly)")
        return cache["sources"]
    except Exception:
        return None


def save_sources_cache(subject, sources):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = get_cache_path(subject)
    cache = {
        "subject": subject,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sources": sources,
    }
    with open(path, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Sources cached to {path}")


def fetch_all_sources(subject, refresh_sources=False):
    cached = None if refresh_sources else load_cached_sources(subject)

    if cached:
        sources = cached
    else:
        print("Discovering best sites for this subject...")
        discovered_sites = discover_best_sites(subject)
        sources = build_sources(subject, discovered_sites)
        save_sources_cache(subject, sources)
    print()

    all_results = {}
    for source in sources:
        print(f"Fetching: {source['name']}...")
        if source.get("type") == "reddit":
            articles = fetch_reddit(source)
        else:
            articles = fetch_rss(source)
        all_results[source["name"]] = {
            "articles": articles,
            "site_url": source["site_url"],
        }
        print(f"  Found {len(articles)} articles")
        time.sleep(0.5)
    return all_results


def deduplicate_articles(all_results):
    """Remove duplicate articles across sources based on title similarity."""
    seen_titles = set()
    for source_name, data in all_results.items():
        unique = []
        for art in data["articles"]:
            normalized = re.sub(r"[^a-z0-9]", "", art["title"].lower())
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique.append(art)
        data["articles"] = unique
    return all_results


def generate_editorial(all_results, subject, run_date, lang_name="English", target_words=600):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARNING] ANTHROPIC_API_KEY not set — skipping editorial summary.")
        return ""

    article_list = []
    for source_name, data in all_results.items():
        for art in data["articles"]:
            article_list.append(
                f"- [{art['title']}]({art['link']}) ({source_name}): {art['summary']}"
            )

    if not article_list:
        return ""

    articles_text = "\n".join(article_list)

    lang_instruction = f"- Write entirely in {lang_name}" if lang_name != "English" else "- Write in English"

    if target_words <= 600:
        length_instruction = "Write a 5-6 paragraph editorial summary"
    elif target_words <= 1500:
        length_instruction = f"Write a detailed editorial of approximately {target_words} words (10-15 paragraphs)"
    else:
        length_instruction = f"Write an in-depth editorial of approximately {target_words} words (15-25+ paragraphs)"

    max_tokens = max(4000, int(target_words * 1.5))

    prompt = f"""You are an expert analyst writing a daily newsletter editorial about "{subject}".
Based on today's ({run_date}) articles below, {length_instruction.lower()}.

Rules:
{lang_instruction}
- Target approximately {target_words} words
- Write in an engaging, professional journalistic tone
- Identify the major themes and trends across all articles related to {subject}
- Embed relevant article links naturally as HTML anchor tags: <a href="URL">descriptive text</a>
- Each paragraph should cover a distinct theme or storyline
- Include at least 8-10 embedded links spread across the paragraphs
- Do NOT use markdown — output raw HTML paragraphs wrapped in <p> tags
- Do NOT include any heading tags — just the <p> paragraphs
- Focus specifically on the {subject} angle of each story

Articles:
{articles_text}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        editorial_html = message.content[0].text
        if message.stop_reason == "end_turn":
            print("Editorial summary generated via Claude API")
        else:
            print(f"[WARNING] Editorial may be incomplete (stop_reason: {message.stop_reason})")
        return editorial_html
    except Exception as e:
        print(f"[WARNING] Failed to generate editorial: {e}")
        return ""


def generate_audio(editorial_html, output_path, voice=None, speed=AUDIO_SPEED):
    if not voice:
        print("[SKIP] Audio disabled.")
        return None

    if not editorial_html:
        print("[SKIP] No editorial content — audio not generated.")
        return None

    plain_text = strip_html(editorial_html)
    if not plain_text.strip():
        return None

    txt_path = output_path.replace(".m4a", ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(plain_text)

    rate = int(200 * speed)

    try:
        subprocess.run(
            ["say", "-v", voice, "-r", str(rate), "-o", output_path, "-f", txt_path],
            check=True, timeout=180,
        )
        os.remove(txt_path)
        compressed = output_path + ".tmp"
        try:
            subprocess.run(
                ["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", output_path, compressed],
                check=True, timeout=60,
            )
            os.replace(compressed, output_path)
        except Exception:
            if os.path.exists(compressed):
                os.remove(compressed)
        print(f"Audio saved: {output_path} (speed: {speed}x)")
        return output_path
    except Exception as e:
        print(f"[WARNING] Audio generation failed: {e}")
        if os.path.exists(txt_path):
            os.remove(txt_path)
        return None


def audio_to_data_uri(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:audio/mp4;base64,{b64}"


def generate_html(all_results, subject, run_date, editorial_html="", audio_src=None):
    source_count = sum(1 for v in all_results.values() if v["articles"])
    article_count = sum(len(v["articles"]) for v in all_results.values())

    sections_html = ""
    for source_name, data in all_results.items():
        articles = data["articles"]
        site_url = data["site_url"]

        if not articles:
            sections_html += f"""
        <div class="source-section empty">
            <div class="source-header">
                <h2><a href="{escape(site_url)}" target="_blank">{escape(source_name)}</a></h2>
            </div>
            <p class="no-articles">No recent articles available</p>
        </div>"""
            continue

        articles_html = ""
        for art in articles:
            articles_html += f"""
                <div class="article">
                    <h3><a href="{escape(art['link'])}" target="_blank">{escape(art['title'])}</a></h3>
                    <span class="date">{escape(art['date'])}</span>
                    <p class="summary">{escape(art['summary'])}</p>
                </div>"""

        sections_html += f"""
        <div class="source-section">
            <div class="source-header">
                <h2><a href="{escape(site_url)}" target="_blank">{escape(source_name)}</a></h2>
                <span class="article-count">{len(articles)} article{"s" if len(articles) != 1 else ""}</span>
            </div>
            {articles_html}
        </div>"""

    subject_escaped = escape(subject)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject_escaped} Briefing - {run_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
            background: #0f0f1a;
            color: #e0e0e0;
            line-height: 1.6;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            border-radius: 16px;
            margin-bottom: 30px;
            border: 1px solid #2a2a4a;
        }}

        header h1 {{
            font-size: 2.4em;
            color: #40E0D0;
            margin-bottom: 8px;
        }}

        header .subtitle {{
            color: #80f0e0;
            font-size: 1.1em;
        }}

        header .stats {{
            margin-top: 15px;
            display: flex;
            justify-content: center;
            gap: 30px;
        }}

        header .stat {{
            background: rgba(255,255,255,0.05);
            padding: 8px 20px;
            border-radius: 20px;
            font-size: 0.9em;
            color: #aaaacc;
        }}

        header .stat strong {{
            color: #00d2ff;
        }}

        .editorial {{
            background: linear-gradient(135deg, #1a1a2e 0%, #1e1e3a 100%);
            border: 1px solid #3a3a5a;
            border-radius: 12px;
            padding: 30px 32px;
            margin-bottom: 30px;
        }}

        .editorial h2 {{
            font-size: 1.5em;
            color: #00d2ff;
            margin-bottom: 18px;
            padding-bottom: 12px;
            border-bottom: 1px solid #2a2a4a;
        }}

        .editorial p {{
            margin-bottom: 14px;
            color: #ccccdd;
            font-size: 1em;
            line-height: 1.75;
        }}

        .editorial p:last-child {{
            margin-bottom: 0;
        }}

        .audio-player {{
            margin-bottom: 18px;
        }}

        .audio-player audio {{
            width: 100%;
            border-radius: 8px;
        }}

        .editorial a {{
            color: #7b9fff;
            text-decoration: none;
            border-bottom: 1px dotted #7b9fff;
        }}

        .editorial a:hover {{
            color: #a0bfff;
            border-bottom-color: #a0bfff;
        }}

        .source-section {{
            background: #1a1a2e;
            border: 1px solid #2a2a4a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }}

        .source-section:hover {{
            border-color: #7b2ff7;
        }}

        .source-section.empty {{
            opacity: 0.5;
        }}

        .source-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #2a2a4a;
        }}

        .source-header h2 {{
            font-size: 1.3em;
        }}

        .source-header h2 a {{
            color: #7b2ff7;
            text-decoration: none;
        }}

        .source-header h2 a:hover {{
            color: #a66bff;
        }}

        .article-count {{
            background: #7b2ff733;
            color: #a66bff;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
        }}

        .article {{
            padding: 14px 0;
            border-bottom: 1px solid #1e1e38;
        }}

        .article:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}

        .article h3 {{
            font-size: 1.05em;
            margin-bottom: 4px;
        }}

        .article h3 a {{
            color: #e0e0e0;
            text-decoration: none;
        }}

        .article h3 a:hover {{
            color: #00d2ff;
        }}

        .article .date {{
            font-size: 0.8em;
            color: #666688;
        }}

        .article .summary {{
            margin-top: 6px;
            color: #9999bb;
            font-size: 0.92em;
        }}

        .no-articles {{
            color: #555577;
            font-style: italic;
        }}

        footer {{
            text-align: center;
            padding: 30px;
            color: #555577;
            font-size: 0.85em;
        }}

        footer a {{
            color: #7b2ff7;
            text-decoration: none;
        }}

        @media (max-width: 600px) {{
            header h1 {{ font-size: 1.8em; }}
            header .stats {{ flex-direction: column; gap: 8px; }}
            .source-header {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{subject_escaped} Daily Briefing</h1>
            <div class="subtitle">{run_date}</div>
            <div class="stats">
                <div class="stat"><strong>{source_count}</strong> sources</div>
                <div class="stat"><strong>{article_count}</strong> articles</div>
            </div>
        </header>

        {f'''<div class="editorial">
            <h2>Editorial Summary</h2>
            {f'<div class="audio-player"><audio controls><source src="{audio_src}" type="audio/mp4">Your browser does not support audio.</audio></div>' if audio_src else ''}
            {editorial_html}
        </div>''' if editorial_html else ''}

        <h2 style="color: #7b2ff7; margin-bottom: 20px; font-size: 1.4em;">All Articles by Source</h2>

        {sections_html}

        <footer>
            Generated on {run_date} by AgentGeneric Newsletter Generator
        </footer>
    </div>
</body>
</html>"""

    return html


def ask_audio():
    print("Audio for editorial narration:")
    print()
    print("  0 — No audio")
    print("  1 — English (default)")
    print("  2 — Turkish")
    print("  3 — French")
    print()
    choice = input("  Select (0-3, default: 1): ").strip()
    if not choice:
        choice = "1"
    if choice not in AUDIO_OPTIONS:
        print(f"  Invalid choice. Using English.")
        choice = "1"
    opt = AUDIO_OPTIONS[choice]
    if opt["voice"]:
        print(f"  Audio: {opt['name']} (voice: {opt['voice']})")
    else:
        print(f"  Audio: disabled")
    return opt


def ask_speed():
    print()
    print("Narration speed:")
    print()
    print("  1 — 0.75x (slow)")
    print("  2 — 1x (normal, default)")
    print("  3 — 1.25x (fast)")
    print()
    choice = input("  Select (1-3, default: 2): ").strip()
    if not choice:
        choice = "2"
    if choice not in SPEED_OPTIONS:
        print(f"  Invalid choice. Using 1x.")
        choice = "2"
    speed = SPEED_OPTIONS[choice]
    print(f"  Speed: {speed}x")
    return speed


def ask_duration():
    print()
    print("Narration duration (minutes):")
    print()
    choice = input("  Enter duration (1-30, default: 3): ").strip()
    if not choice:
        duration = 3
    else:
        try:
            duration = int(choice)
            if duration < 1:
                duration = 1
            elif duration > 30:
                duration = 30
        except ValueError:
            print(f"  Invalid input. Using 3 minutes.")
            duration = 3
    print(f"  Duration: {duration} min")
    return duration


KNOWN_DOMAINS = [
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.co.jp",
    "outlook.com", "hotmail.com", "live.com", "msn.com", "aol.com",
    "icloud.com", "me.com", "mac.com", "mail.com", "protonmail.com",
    "proton.me", "zoho.com", "yandex.com", "gmx.com", "gmx.net",
    "fastmail.com", "tutanota.com", "hey.com", "pm.me",
]


def validate_email(email):
    email = email.strip().lower()
    if "@" not in email:
        return None, "Missing '@' sign"
    parts = email.split("@")
    if len(parts) != 2:
        return None, "Multiple '@' signs"
    local, domain = parts
    if not local:
        return None, "No username before '@'"
    if not domain:
        return None, "No domain after '@'"
    if "." not in domain:
        return None, f"Invalid domain '{domain}' — missing top-level domain (e.g., .com)"
    domain_parts = domain.split(".")
    if any(len(p) == 0 for p in domain_parts):
        return None, f"Invalid domain '{domain}' — empty segment"
    if len(domain_parts[-1]) < 2:
        return None, f"Invalid domain '{domain}' — top-level domain too short"
    return email, None


def collect_emails():
    print("Enter recipient email addresses (up to 10). Press Enter with no input to finish.")
    print()
    emails = []
    for i in range(1, 11):
        raw = input(f"  Email {i}: ").strip()
        if not raw:
            break
        email, error = validate_email(raw)
        if error:
            print(f"    [INVALID] {error}. Skipped.")
            continue
        if email in emails:
            print(f"    [DUPLICATE] Already added. Skipped.")
            continue
        emails.append(email)
        print(f"    [OK] {email}")
    return emails


def send_email(html_content, subject, run_date, recipients, audio_bytes=None, audio_filename=None):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        print("[ERROR] GMAIL_APP_PASSWORD environment variable not set.")
        return False

    if not recipients:
        print("[SKIP] No recipients — email not sent.")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"{subject} Daily Briefing - {run_date}"
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)

    alt_part = MIMEMultipart("alternative")
    plain_text = f"{subject} Daily Briefing for {run_date}. Open in a browser for the full newsletter."
    alt_part.attach(MIMEText(plain_text, "plain"))

    if audio_bytes:
        email_html = re.sub(
            r'<div class="audio-player">.*?</div>',
            '<p style="color: #80f0e0; font-style: italic; margin-bottom: 14px;">Audio narration attached to this email.</p>',
            html_content, flags=re.DOTALL,
        )
    else:
        email_html = re.sub(r'<div class="audio-player">.*?</div>', '', html_content, flags=re.DOTALL)
    alt_part.attach(MIMEText(email_html, "html", "utf-8"))
    msg.attach(alt_part)

    if audio_bytes and audio_filename:
        audio_part = MIMEBase("audio", "mp4")
        audio_part.set_payload(audio_bytes)
        encoders.encode_base64(audio_part)
        audio_part.add_header("Content-Disposition", "attachment", filename=audio_filename)
        msg.attach(audio_part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, app_password)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
        print(f"Email sent to: {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


def sanitize_filename(subject):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", subject).strip("_")


def ask_schedule():
    print("Would you like to schedule this newsletter periodically?")
    choice = input("  (d)aily / (w)eekly / (n)o: ").strip().lower()

    if choice in ("d", "daily"):
        period = "daily"
    elif choice in ("w", "weekly"):
        period = "weekly"
    else:
        return None, None, None

    while True:
        time_str = input("  At what time? (HH:MM in 24h format, e.g. 08:00): ").strip()
        match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                break
        print("    Invalid time. Please use HH:MM format (e.g., 08:00, 14:30)")

    day_of_week = None
    if period == "weekly":
        days = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
        while True:
            day_input = input("  Which day? (Mon/Tue/Wed/Thu/Fri/Sat/Sun): ").strip().lower()[:3]
            if day_input in days:
                day_of_week = days[day_input]
                break
            print("    Invalid day. Please enter e.g., Mon, Tue, Wed...")

    return period, (hour, minute), day_of_week


def setup_cron(subject, recipients, period, schedule_time, day_of_week=None, lang_code="en"):
    safe_name = sanitize_filename(subject)
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    env_path = os.path.join(SCRIPT_DIR, ".env")
    log_path = os.path.join(SCRIPT_DIR, f"newsletter_{safe_name}.log")

    hour, minute = schedule_time
    recipients_arg = ",".join(recipients)

    if period == "weekly" and day_of_week is not None:
        cron_schedule = f"{minute} {hour} * * {day_of_week}"
    else:
        cron_schedule = f"{minute} {hour} * * *"

    cron_line = (
        f'{cron_schedule} cd {SCRIPT_DIR} && '
        f'{python_path} {script_path} '
        f'--subject "{subject}" --recipients "{recipients_arg}" --lang "{lang_code}" '
        f'>> {log_path} 2>&1'
    )

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout.strip()

        marker = f'AgentGeneric:{safe_name}'
        cron_entry = f'{cron_line} # {marker}'

        lines = existing.split("\n") if existing else []
        lines = [l for l in lines if marker not in l]
        lines.append(cron_entry)

        new_crontab = "\n".join(lines) + "\n"
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)

        day_names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
        if period == "weekly":
            schedule_desc = f"weekly on {day_names.get(day_of_week, '?')} at {hour:02d}:{minute:02d}"
        else:
            schedule_desc = f"daily at {hour:02d}:{minute:02d}"
        print(f"Cron job added: {schedule_desc} for '{subject}'")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to set up cron: {e}")
        return False


def list_scheduled_jobs():
    """Parse cron and return detailed info for all AgentGeneric and newsletter jobs."""
    day_names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
    jobs = []
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return jobs
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 6:
                continue

            minute, hour, dom, month, dow = parts[0:5]
            rest = " ".join(parts[5:])

            # Determine schedule description
            if hour == "*" or minute == "*":
                schedule = "Hourly at :00"
            elif dow != "*" and dom == "*":
                day_name = day_names.get(int(dow), dow)
                schedule = f"Weekly on {day_name} at {int(hour):02d}:{int(minute):02d}"
            else:
                schedule = f"Daily at {int(hour):02d}:{int(minute):02d}"

            # Parse marker
            marker_match = re.search(r"# (?:AgentGeneric|Magent):(.+)$", line)
            if marker_match:
                subject = marker_match.group(1).replace("_", " ")
                recip_match = re.search(r'--recipients\s+"([^"]+)"', line)
                recipients = recip_match.group(1).split(",") if recip_match else []
                job_type = "Magent" if "Magent.py" in line else "AgentGeneric"
                jobs.append({
                    "type": job_type,
                    "subject": subject,
                    "schedule": schedule,
                    "recipients": recipients,
                    "marker": f"AgentGeneric:{marker_match.group(1)}",
                    "line": line,
                })
            elif "ai_newsletter.py" in line:
                jobs.append({
                    "type": "AI Newsletter",
                    "subject": "AI (ai_newsletter.py)",
                    "schedule": schedule,
                    "recipients": [EMAIL_TO],
                    "marker": "__ai_newsletter__",
                    "line": line,
                })
            elif "newsletter_watchdog.py" in line:
                continue
    except Exception:
        pass
    return jobs


def display_and_manage_jobs():
    """Show all scheduled newsletter jobs and offer removal. Returns True if any were removed."""
    jobs = list_scheduled_jobs()
    if not jobs:
        return False

    print("Scheduled newsletters:")
    print("-" * 50)
    for i, job in enumerate(jobs, 1):
        recip_str = ", ".join(job["recipients"][:3])
        if len(job["recipients"]) > 3:
            recip_str += f" (+{len(job['recipients']) - 3} more)"
        print(f"  {i}. [{job['type']}] {job['subject']}")
        print(f"     Schedule:   {job['schedule']}")
        if recip_str:
            print(f"     Recipients: {recip_str}")
    print("-" * 50)
    print()

    remove_input = input("Enter numbers to remove (e.g., 1,3), or press Enter to keep all: ").strip()
    if not remove_input:
        print("  All jobs kept.")
        return False

    to_remove = set()
    for part in remove_input.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(jobs):
                to_remove.add(idx)

    if not to_remove:
        print("  No valid selections. All jobs kept.")
        return False

    # Confirm removal
    print()
    print("  Will remove:")
    for idx in sorted(to_remove):
        job = jobs[idx - 1]
        print(f"    - {job['subject']} ({job['schedule']})")

    confirm = input("  Confirm removal? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Removal cancelled.")
        return False

    # Remove selected jobs from crontab
    markers_to_remove = set()
    for idx in to_remove:
        markers_to_remove.add(jobs[idx - 1]["marker"])

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        new_lines = []
        for line in lines:
            remove_this = False
            for marker in markers_to_remove:
                if marker == "__ai_newsletter__":
                    if "ai_newsletter.py" in line:
                        remove_this = True
                        break
                elif marker in line:
                    remove_this = True
                    break
            if not remove_this:
                new_lines.append(line)

        if new_lines:
            new_crontab = "\n".join(new_lines) + "\n"
        else:
            new_crontab = ""

        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        print(f"  Removed {len(to_remove)} job(s).")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to update crontab: {e}")
        return False


def print_summary(subject, recipients, period, schedule_time, day_of_week, lang_name="English", audio_name="None", speed=AUDIO_SPEED, duration=3):
    day_names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}

    print()
    print("=" * 50)
    print("  REVIEW — Please confirm before proceeding")
    print("=" * 50)
    print()
    print(f"  Subject:      {subject}")
    print(f"  Language:     {lang_name}")
    print(f"  Audio:        {audio_name}")
    if audio_name != "No audio":
        print(f"  Speed:        {speed}x")
        print(f"  Duration:     {duration} min")
    print()
    print(f"  Recipients:   ({len(recipients)})")
    for email in recipients:
        print(f"                  - {email}")
    print()
    if period:
        hour, minute = schedule_time
        if period == "weekly":
            print(f"  Schedule:     Weekly on {day_names.get(day_of_week, '?')} at {hour:02d}:{minute:02d}")
        else:
            print(f"  Schedule:     Daily at {hour:02d}:{minute:02d}")
        print(f"  First send:   NOW (test run)")
    else:
        print(f"  Schedule:     One-time send (no recurring schedule)")
    print()
    print("=" * 50)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AgentGeneric — Subject-based newsletter generator")
    parser.add_argument("quick_subject", nargs="?", type=str, default=None, help="Subject for quick mode (auto-approved, English, slow speed, emailed to default recipient)")
    parser.add_argument("--subject", type=str, help="Subject to research (non-interactive mode)")
    parser.add_argument("--recipients", type=str, help="Comma-separated recipient emails (non-interactive)")
    parser.add_argument("--lang", type=str, default="1", help="Audio option: 0=none, 1=English, 2=Turkish, 3=French")
    parser.add_argument("--speed", type=str, default="2", help="Audio speed: 1=0.75x, 2=1x (default), 3=1.25x")
    parser.add_argument("--duration", type=int, default=3, help="Audio narration duration in minutes (1-30, default: 3)")
    parser.add_argument("--refresh-sources", action="store_true", help="Force rediscovery of sources (ignore cache)")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    args = parser.parse_args()

    quick_mode = args.quick_subject is not None and args.subject is None
    is_interactive = args.subject is None and not quick_mode

    if quick_mode or is_interactive:
        print("=" * 50)
        if quick_mode:
            print("  AgentGeneric — Quick Mode")
        else:
            print("  AgentGeneric — Newsletter Generator")
        print("=" * 50)
        print()

        display_and_manage_jobs()
        print()

    if quick_mode:
        subject = args.quick_subject
        audio_opt = AUDIO_OPTIONS["1"]
        speed = SPEED_OPTIONS["1"]
        duration = 3
        recipients = [EMAIL_TO]
        period, schedule_time, day_of_week = None, None, None
        print(f"  Quick mode: \"{subject}\"")
        print(f"  English | 0.75x speed | 3 min | {EMAIL_TO}")
        print("=" * 50)
    elif is_interactive:

        subject = input("Enter the subject of inquiry: ").strip()
        if not subject:
            print("No subject provided. Exiting.")
            sys.exit(1)

        print()
        audio_opt = ask_audio()
        if audio_opt["voice"]:
            speed = ask_speed()
            duration = ask_duration()
        else:
            speed = AUDIO_SPEED
            duration = 3
    else:
        subject = args.subject
        audio_opt = AUDIO_OPTIONS.get(args.lang, AUDIO_OPTIONS["1"])
        speed = SPEED_OPTIONS.get(args.speed, SPEED_OPTIONS["2"])
        duration = max(1, min(30, args.duration))

    lang_name = audio_opt["lang_name"] or "English"
    voice = audio_opt["voice"]

    if not quick_mode:
        # Determine recipients
        if args.recipients:
            recipients = [e.strip() for e in args.recipients.split(",") if e.strip()]
        elif is_interactive:
            print()
            recipients = collect_emails()
            if not recipients:
                print("  No valid emails entered. Newsletter will be saved but not emailed.")
        else:
            recipients = [EMAIL_TO]

        # Ask about scheduling (interactive only)
        period, schedule_time, day_of_week = None, None, None
        if is_interactive and recipients:
            print()
            period, schedule_time, day_of_week = ask_schedule()

        # Show review summary and ask for confirmation (interactive only)
        if is_interactive:
            print_summary(subject, recipients, period, schedule_time, day_of_week, lang_name, audio_opt["name"], speed, duration)
            confirm = input("  Proceed? (y/n): ").strip().lower()
            if confirm not in ("y", "yes"):
                print("\n  Cancelled.")
                sys.exit(0)

    # Fetch and generate
    run_date = datetime.now().strftime("%Y-%m-%d")
    safe_name = sanitize_filename(subject)
    filename = os.path.join(
        SCRIPT_DIR,
        f"{safe_name}_{run_date}.html",
    )

    print()
    print(f"Subject: {subject}")
    print(f"Date:    {run_date}")
    print("-" * 50)
    print()

    all_results = fetch_all_sources(subject, refresh_sources=args.refresh_sources)
    all_results = deduplicate_articles(all_results)

    print()
    print("Generating editorial summary...")
    target_words = int(duration * 200 * speed)
    editorial_html = generate_editorial(all_results, subject, run_date, lang_name, target_words)

    print("Generating audio narration...")
    audio_path = os.path.join(
        SCRIPT_DIR,
        f"{safe_name}_{run_date}.m4a",
    )
    audio_file = generate_audio(editorial_html, audio_path, voice, speed)

    audio_src = None
    audio_bytes = None
    audio_filename = None
    if audio_file:
        with open(audio_file, "rb") as f:
            audio_bytes = f.read()
        audio_src = audio_to_data_uri(audio_bytes)
        audio_filename = os.path.basename(audio_file)
        os.remove(audio_file)
        print(f"Audio embedded in HTML, file cleaned up: {audio_filename}")

    print("Generating HTML newsletter...")
    html = generate_html(all_results, subject, run_date, editorial_html, audio_src)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    total = sum(len(v["articles"]) for v in all_results.values())
    print(f"Newsletter saved: {filename}")
    print(f"Total articles: {total}")

    # Send email
    if not args.no_email and recipients:
        print()
        send_email(html, subject, run_date, recipients, audio_bytes, audio_filename)

    # Set up cron if periodic (interactive only)
    if is_interactive and period and schedule_time and recipients:
        print()
        setup_cron(subject, recipients, period, schedule_time, day_of_week, audio_opt["code"])

    print("\nDone!")


if __name__ == "__main__":
    main()

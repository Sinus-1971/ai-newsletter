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
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

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


def fetch_all_sources(subject):
    print("Discovering best sites for this subject...")
    discovered_sites = discover_best_sites(subject)
    sources = build_sources(subject, discovered_sites)
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


def generate_editorial(all_results, subject, run_date):
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

    prompt = f"""You are an expert analyst writing a daily newsletter editorial about "{subject}".
Based on today's ({run_date}) articles below, write a 5-6 paragraph editorial summary.

Rules:
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
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        editorial_html = message.content[0].text
        print("Editorial summary generated via Claude API")
        return editorial_html
    except Exception as e:
        print(f"[WARNING] Failed to generate editorial: {e}")
        return ""


def generate_html(all_results, subject, run_date, editorial_html=""):
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
            background: linear-gradient(90deg, #00d2ff, #7b2ff7, #ff6b9d);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }}

        header .subtitle {{
            color: #8888aa;
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


def send_email(html_content, subject, run_date):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        print("[ERROR] GMAIL_APP_PASSWORD environment variable not set.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{subject} Daily Briefing - {run_date}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    plain_text = f"{subject} Daily Briefing for {run_date}. Open in a browser for the full newsletter."
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, app_password)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"Email sent to {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


def sanitize_filename(subject):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", subject).strip("_")


def setup_cron(subject):
    safe_name = sanitize_filename(subject)
    script_path = os.path.abspath(__file__)
    python_path = sys.executable

    cron_line = (
        f'0 8 * * * export GMAIL_APP_PASSWORD="$(cat /Users/sinan/projects/Orchestrator/files2/.env '
        f'| grep GMAIL_APP_PASSWORD | cut -d\\\" -f2)" && '
        f'export ANTHROPIC_API_KEY="$(cat /Users/sinan/projects/Orchestrator/files2/.env '
        f'| grep ANTHROPIC_API_KEY | cut -d\\\" -f2)" && '
        f'{python_path} {script_path} --subject "{subject}" '
        f'>> /Users/sinan/projects/Orchestrator/files2/newsletter_{safe_name}.log 2>&1'
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
        print(f"Cron job added: daily at 8:00 AM for '{subject}'")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to set up cron: {e}")
        return False


def list_scheduled_subjects():
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        subjects = []
        for line in lines:
            match = re.search(r"# AgentGeneric:(.+)$", line)
            if match:
                subjects.append(match.group(1).replace("_", " "))
        return subjects
    except Exception:
        return []


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AgentGeneric — Subject-based newsletter generator")
    parser.add_argument("--subject", type=str, help="Subject to research (non-interactive mode)")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    parser.add_argument("--no-cron", action="store_true", help="Skip cron scheduling prompt")
    args = parser.parse_args()

    if args.subject:
        subject = args.subject
    else:
        print("=" * 50)
        print("  AgentGeneric — Newsletter Generator")
        print("=" * 50)
        print()

        scheduled = list_scheduled_subjects()
        if scheduled:
            print("Currently scheduled subjects:")
            for s in scheduled:
                print(f"  - {s}")
            print()

        subject = input("Enter the subject of inquiry: ").strip()
        if not subject:
            print("No subject provided. Exiting.")
            sys.exit(1)

    run_date = datetime.now().strftime("%Y-%m-%d")
    safe_name = sanitize_filename(subject)
    filename = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"{safe_name}_{run_date}.html",
    )

    print()
    print(f"Subject: {subject}")
    print(f"Date:    {run_date}")
    print("-" * 50)
    print()

    all_results = fetch_all_sources(subject)
    all_results = deduplicate_articles(all_results)

    print()
    print("Generating editorial summary...")
    editorial_html = generate_editorial(all_results, subject, run_date)

    print("Generating HTML newsletter...")
    html = generate_html(all_results, subject, run_date, editorial_html)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    total = sum(len(v["articles"]) for v in all_results.values())
    print(f"Newsletter saved: {filename}")
    print(f"Total articles: {total}")

    if not args.no_email:
        print()
        send_email(html, subject, run_date)

    if not args.no_cron and not args.subject:
        print()
        schedule = input("Schedule this subject to run daily? (y/n): ").strip().lower()
        if schedule in ("y", "yes"):
            setup_cron(subject)

    print()
    print("Done!")


if __name__ == "__main__":
    main()

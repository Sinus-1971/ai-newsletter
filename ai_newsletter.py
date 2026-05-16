#!/usr/bin/env python3
"""
AI Newsletter Generator
Fetches articles from 10 top AI news sources, generates an editorial summary
via Claude API, and produces a styled HTML newsletter emailed daily.

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

AI_NEWS_SOURCES = [
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "site_url": "https://techcrunch.com/category/artificial-intelligence/",
        "type": "rss",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "site_url": "https://www.theverge.com/ai-artificial-intelligence",
        "type": "rss",
    },
    {
        "name": "Ars Technica AI",
        "url": "https://arstechnica.com/feed/",
        "site_url": "https://arstechnica.com/ai/",
        "type": "rss",
        "filter_keywords": ["ai", "artificial intelligence", "machine learning", "llm",
                            "gpt", "claude", "gemini", "neural", "deep learning",
                            "openai", "anthropic", "google ai", "chatbot"],
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "site_url": "https://venturebeat.com/category/ai/",
        "type": "rss",
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "site_url": "https://www.technologyreview.com/topic/artificial-intelligence/",
        "type": "rss",
        "filter_keywords": ["ai", "artificial intelligence", "machine learning", "llm",
                            "neural", "deep learning", "openai", "anthropic", "model"],
    },
    {
        "name": "Wired AI",
        "url": "https://www.wired.com/feed/tag/ai/latest/rss",
        "site_url": "https://www.wired.com/tag/artificial-intelligence/",
        "type": "rss",
    },
    {
        "name": "The Register AI",
        "url": "https://www.theregister.com/headlines.atom",
        "site_url": "https://www.theregister.com/",
        "type": "rss",
        "filter_keywords": ["ai", "artificial intelligence", "machine learning", "llm",
                            "gpt", "claude", "gemini", "neural", "deep learning",
                            "openai", "anthropic", "google ai", "chatbot", "copilot"],
    },
    {
        "name": "Google AI Blog",
        "url": "https://blog.google/technology/ai/rss/",
        "site_url": "https://blog.google/technology/ai/",
        "type": "rss",
    },
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "site_url": "https://openai.com/blog",
        "type": "rss",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "site_url": "https://huggingface.co/blog",
        "type": "rss",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MAX_ARTICLES_PER_SOURCE = 5


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


def fetch_all_sources():
    all_results = {}
    for source in AI_NEWS_SOURCES:
        print(f"Fetching: {source['name']}...")
        articles = fetch_rss(source)
        all_results[source["name"]] = {
            "articles": articles,
            "site_url": source["site_url"],
        }
        print(f"  Found {len(articles)} articles")
        time.sleep(0.5)
    return all_results


def generate_editorial(all_results, run_date):
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

    prompt = f"""You are an expert AI industry analyst writing a daily newsletter editorial.
Based on today's ({run_date}) AI news articles below, write a 5-6 paragraph editorial summary.

Rules:
- Write in an engaging, professional journalistic tone
- Identify the major themes and trends across all articles
- Embed relevant article links naturally as HTML anchor tags: <a href="URL">descriptive text</a>
- Each paragraph should cover a distinct theme or storyline
- Include at least 8-10 embedded links spread across the paragraphs
- Do NOT use markdown — output raw HTML paragraphs wrapped in <p> tags
- Do NOT include any heading tags — just the <p> paragraphs

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


def generate_audio(editorial_html, output_path, voice="Samantha", speed=1.25):
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


def generate_html(all_results, run_date, editorial_html="", audio_src=None):
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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Newsletter - {run_date}</title>
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
            <h1>AI Daily Briefing</h1>
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
            Generated on {run_date} by AI Newsletter Generator
        </footer>
    </div>
</body>
</html>"""

    return html


def send_email(html_content, run_date, audio_bytes=None, audio_filename=None):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        print("[ERROR] GMAIL_APP_PASSWORD environment variable not set.")
        print("  Set it with: export GMAIL_APP_PASSWORD='your-app-password'")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"AI Daily Briefing - {run_date}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    alt_part = MIMEMultipart("alternative")
    plain_text = f"AI Daily Briefing for {run_date}. Open in a browser for the full newsletter."
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
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"Email sent to {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


def main():
    run_date = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(SCRIPT_DIR, f"Sites_{run_date}.html")

    print("=" * 50)
    print(f"  AI Newsletter Generator - {run_date}")
    print("=" * 50)
    print()

    all_results = fetch_all_sources()

    print()
    print("Generating editorial summary...")
    editorial_html = generate_editorial(all_results, run_date)

    print("Generating audio narration...")
    audio_path = os.path.join(SCRIPT_DIR, f"Sites_{run_date}.m4a")
    audio_file = generate_audio(editorial_html, audio_path)

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
    html = generate_html(all_results, run_date, editorial_html, audio_src)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    total = sum(len(v["articles"]) for v in all_results.values())
    print(f"Newsletter saved: {filename}")
    print(f"Total articles: {total}")

    print()
    send_email(html, run_date, audio_bytes, audio_filename)

    print("Done!")


if __name__ == "__main__":
    main()

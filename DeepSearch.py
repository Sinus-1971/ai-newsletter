#!/usr/bin/env python3
"""
DeepSearch — Academic and authoritative resource newsletter generator.
Searches academic papers (arXiv, Semantic Scholar, PubMed), well-known
resources, and research news. Produces a 1000+ word digest with infographics,
formal references, and Microsoft Edge neural TTS narration of the editorial.

Setup:
  export GMAIL_APP_PASSWORD="your-app-password-here"
  export ANTHROPIC_API_KEY="your-anthropic-api-key"
  pip install edge-tts feedparser requests anthropic python-dotenv
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
import asyncio
import base64
import edge_tts
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

MAX_PAPERS_PER_SOURCE = 10

AUDIO_OPTIONS = {
    "0": {"name": "No audio",  "voice": None,                  "lang_name": None,      "code": "0"},
    "1": {"name": "English",   "voice": "en-US-AriaNeural",    "lang_name": "English", "code": "1"},
    "2": {"name": "Turkish",   "voice": "tr-TR-EmelNeural",    "lang_name": "Turkish", "code": "2"},
    "3": {"name": "French",    "voice": "fr-FR-DeniseNeural",  "lang_name": "French",  "code": "3"},
}

AUDIO_SPEED = 1.0

SPEED_OPTIONS = {
    "1": 0.75,
    "2": 1.0,
    "3": 1.25,
}


# --- Academic Source Fetchers ---

def fetch_arxiv(subject, max_results=MAX_PAPERS_PER_SOURCE):
    encoded = quote_plus(subject)
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    papers = []
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:max_results]:
            authors = ", ".join(a.get("name", "") for a in entry.get("authors", [])[:5])
            if len(entry.get("authors", [])) > 5:
                authors += " et al."
            pub_date = None
            if entry.get("published_parsed"):
                try:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            summary = re.sub(r"\s+", " ", entry.get("summary", "")).strip()
            papers.append({
                "title": entry.get("title", "").replace("\n", " ").strip(),
                "link": entry.get("link", ""),
                "authors": authors,
                "summary": summary[:400] + "..." if len(summary) > 400 else summary,
                "date": pub_date.strftime("%b %d, %Y") if pub_date else "",
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
                "source": "arXiv",
            })
    except Exception as e:
        print(f"  [WARNING] arXiv fetch failed: {e}")
    return papers


def fetch_semantic_scholar(subject, max_results=MAX_PAPERS_PER_SOURCE):
    encoded = quote_plus(subject)
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded}&limit={max_results}&fields=title,authors,year,abstract,url,citationCount,publicationDate"
    papers = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        for paper in data.get("data", [])[:max_results]:
            authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:5])
            if len(paper.get("authors") or []) > 5:
                authors += " et al."
            pub_date = None
            if paper.get("publicationDate"):
                try:
                    pub_date = datetime.strptime(paper["publicationDate"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            abstract = (paper.get("abstract") or "")[:400]
            if len(paper.get("abstract") or "") > 400:
                abstract += "..."
            papers.append({
                "title": paper.get("title", "Untitled"),
                "link": paper.get("url") or f"https://www.semanticscholar.org/",
                "authors": authors,
                "summary": abstract or "No abstract available",
                "date": pub_date.strftime("%b %d, %Y") if pub_date else str(paper.get("year", "")),
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
                "source": "Semantic Scholar",
                "citations": paper.get("citationCount", 0),
            })
    except Exception as e:
        print(f"  [WARNING] Semantic Scholar fetch failed: {e}")
    return papers


def fetch_pubmed(subject, max_results=MAX_PAPERS_PER_SOURCE):
    encoded = quote_plus(subject)
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={encoded}&retmax={max_results}&sort=date&retmode=json"
    papers = []
    try:
        resp = requests.get(search_url, timeout=15)
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return papers

        ids_str = ",".join(ids)
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        resp2 = requests.get(fetch_url, timeout=15)
        resp2.raise_for_status()
        results = resp2.json().get("result", {})

        for pmid in ids:
            paper = results.get(pmid, {})
            if not isinstance(paper, dict):
                continue
            authors_list = paper.get("authors", [])
            authors = ", ".join(a.get("name", "") for a in authors_list[:5])
            if len(authors_list) > 5:
                authors += " et al."
            pub_date = None
            if paper.get("pubdate"):
                try:
                    pub_date = datetime.strptime(paper["pubdate"][:10], "%Y/%m/%d").replace(tzinfo=timezone.utc)
                except Exception:
                    try:
                        pub_date = datetime.strptime(paper["pubdate"][:7], "%Y %b").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
            papers.append({
                "title": paper.get("title", "Untitled"),
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "authors": authors,
                "summary": paper.get("title", ""),
                "date": pub_date.strftime("%b %d, %Y") if pub_date else paper.get("pubdate", ""),
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
                "source": "PubMed",
            })
    except Exception as e:
        print(f"  [WARNING] PubMed fetch failed: {e}")
    return papers


def fetch_google_scholar_rss(subject, max_results=MAX_PAPERS_PER_SOURCE):
    encoded = quote_plus(subject)
    url = f"https://news.google.com/rss/search?q={encoded}+site:scholar.google.com+OR+site:researchgate.net+OR+site:doi.org&hl=en&gl=US&ceid=US:en"
    papers = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:max_results]:
            pub_date = None
            if entry.get("published_parsed"):
                try:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            papers.append({
                "title": entry.get("title", "No Title"),
                "link": entry.get("link", ""),
                "authors": "",
                "summary": re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:300],
                "date": pub_date.strftime("%b %d, %Y") if pub_date else "",
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
                "source": "Google Scholar/News",
            })
    except Exception as e:
        print(f"  [WARNING] Google Scholar RSS failed: {e}")
    return papers


def fetch_research_news(subject, max_results=MAX_PAPERS_PER_SOURCE):
    encoded = quote_plus(subject + " research paper study")
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    papers = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:max_results]:
            pub_date = None
            if entry.get("published_parsed"):
                try:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            papers.append({
                "title": entry.get("title", "No Title"),
                "link": entry.get("link", ""),
                "authors": "",
                "summary": re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:300],
                "date": pub_date.strftime("%b %d, %Y") if pub_date else "",
                "sort_date": pub_date or datetime.min.replace(tzinfo=timezone.utc),
                "source": "Research News",
            })
    except Exception as e:
        print(f"  [WARNING] Research news fetch failed: {e}")
    return papers


def fetch_all_academic(subject):
    all_papers = {}

    print(f"Fetching: arXiv...")
    arxiv_papers = fetch_arxiv(subject)
    all_papers["arXiv"] = {"articles": arxiv_papers, "site_url": "https://arxiv.org/"}
    print(f"  Found {len(arxiv_papers)} papers")

    time.sleep(1)

    print(f"Fetching: Semantic Scholar...")
    ss_papers = fetch_semantic_scholar(subject)
    all_papers["Semantic Scholar"] = {"articles": ss_papers, "site_url": "https://www.semanticscholar.org/"}
    print(f"  Found {len(ss_papers)} papers")

    time.sleep(1)

    print(f"Fetching: PubMed...")
    pubmed_papers = fetch_pubmed(subject)
    all_papers["PubMed"] = {"articles": pubmed_papers, "site_url": "https://pubmed.ncbi.nlm.nih.gov/"}
    print(f"  Found {len(pubmed_papers)} papers")

    time.sleep(0.5)

    print(f"Fetching: Google Scholar / Research News...")
    scholar_papers = fetch_google_scholar_rss(subject)
    all_papers["Google Scholar"] = {"articles": scholar_papers, "site_url": "https://scholar.google.com/"}
    print(f"  Found {len(scholar_papers)} results")

    time.sleep(0.5)

    print(f"Fetching: Research News...")
    news_papers = fetch_research_news(subject)
    all_papers["Research News"] = {"articles": news_papers, "site_url": "https://news.google.com/"}
    print(f"  Found {len(news_papers)} articles")

    return all_papers


def deduplicate_papers(all_results):
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


# --- Editorial & Infographics Generation ---

def generate_editorial(all_results, subject, run_date, lang_name="English"):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARNING] ANTHROPIC_API_KEY not set — skipping editorial.")
        return ""

    paper_list = []
    for source_name, data in all_results.items():
        for art in data["articles"]:
            authors_str = f" by {art['authors']}" if art.get("authors") else ""
            paper_list.append(
                f"- [{art['title']}]({art['link']}){authors_str} ({source_name}, {art['date']}): {art['summary']}"
            )

    if not paper_list:
        return ""

    papers_text = "\n".join(paper_list)
    lang_instruction = f"- Write entirely in {lang_name}" if lang_name != "English" else "- Write in English"

    prompt = f"""You are an expert academic analyst writing a deep research digest about "{subject}".
Based on the academic papers and research articles below (from {run_date}), write a comprehensive 10-paragraph editorial digest.

Rules:
{lang_instruction}
- Write EXACTLY 10 paragraphs, each substantial (100-150 words each), totaling at least 1000 words
- Paragraph 1: Executive overview of the current state of research in {subject}
- Paragraphs 2-4: Key findings and breakthroughs from the most significant papers
- Paragraphs 5-6: Methodological trends and novel approaches observed
- Paragraphs 7-8: Cross-disciplinary connections and broader implications
- Paragraph 9: Gaps in current research and open questions
- Paragraph 10: Future outlook and emerging directions
- Write in an authoritative academic yet accessible tone
- Embed relevant paper links naturally as HTML anchor tags: <a href="URL">descriptive text</a>
- Include at least 15 embedded links spread across the paragraphs
- Do NOT use markdown — output raw HTML paragraphs wrapped in <p> tags
- Do NOT include any heading tags — just the <p> paragraphs
- Reference specific findings, methodologies, and conclusions from the papers

Papers and sources:
{papers_text}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        editorial_html = message.content[0].text
        if message.stop_reason == "end_turn":
            print("Editorial digest generated via Claude API")
        else:
            print(f"[WARNING] Editorial may be incomplete (stop_reason: {message.stop_reason})")
        return editorial_html
    except Exception as e:
        print(f"[WARNING] Failed to generate editorial: {e}")
        return ""


def generate_infographics(all_results, subject, run_date, lang_name="English"):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ""

    paper_list = []
    for source_name, data in all_results.items():
        for art in data["articles"]:
            citations = art.get("citations", "N/A")
            paper_list.append(f"- {art['title']} ({source_name}, {art['date']}, citations: {citations})")

    papers_text = "\n".join(paper_list[:30])

    prompt = f"""Based on these academic papers about "{subject}", generate HTML infographic elements.
Create 3-4 infographic sections using ONLY HTML and inline CSS (no JavaScript, no external resources).

Include these types of visual elements:
1. A "Key Statistics" panel with 3-4 stat boxes (paper count, source breakdown, trending topics)
2. A "Research Landscape" panel showing top 5 themes/topics as colored tags with relative importance
3. A "Top Papers" panel highlighting 3 most significant papers with citation counts
4. A "Trend Indicators" panel with 2-3 arrows/indicators showing research direction

Use this color scheme:
- Background: #1a1a2e
- Accent: #00d2ff (cyan), #7b2ff7 (purple), #40E0D0 (turquoise)
- Text: #e0e0e0
- Cards: #2a2a4a with subtle borders

Output ONLY raw HTML (no markdown, no ```). Use inline styles on every element.
Make it visually striking with gradients, rounded corners, and clean layout.
Total papers analyzed: {sum(len(d['articles']) for d in all_results.values())}
Sources: {', '.join(all_results.keys())}

Papers:
{papers_text}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        infographics_html = message.content[0].text
        if "```" in infographics_html:
            match = re.search(r"```html?\s*(.*?)```", infographics_html, re.DOTALL)
            if match:
                infographics_html = match.group(1)
        print("Infographics generated via Claude API")
        return infographics_html
    except Exception as e:
        print(f"[WARNING] Failed to generate infographics: {e}")
        return ""


# --- References ---

def build_references(all_results):
    refs = []
    idx = 1
    for source_name, data in all_results.items():
        for art in data["articles"]:
            authors = art.get("authors", "")
            title = art["title"]
            date = art.get("date", "n.d.")
            link = art["link"]
            ref_line = f'[{idx}] {authors}{"." if authors else ""} "{title}." <em>{source_name}</em>, {date}. <a href="{escape(link)}" target="_blank">{escape(link)}</a>'
            refs.append(ref_line)
            idx += 1
    return refs


# --- Audio ---

def strip_html(text):
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


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

    rate_pct = int((speed - 1.0) * 100)
    rate_str = f"{rate_pct:+d}%"

    async def _generate():
        communicate = edge_tts.Communicate(plain_text, voice, rate=rate_str)
        await communicate.save(output_path)

    try:
        asyncio.run(_generate())
        print(f"Audio saved: {output_path} (voice: {voice}, speed: {speed}x)")
        return output_path
    except Exception as e:
        print(f"[WARNING] Audio generation failed: {e}")
        return None


def audio_to_data_uri(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:audio/mpeg;base64,{b64}"


# --- HTML Generation ---

def generate_html(all_results, subject, run_date, editorial_html="", infographics_html="", references=None, audio_src=None):
    total_papers = sum(len(d["articles"]) for d in all_results.values())
    source_count = sum(1 for d in all_results.values() if d["articles"])

    refs_html = ""
    if references:
        refs_items = "\n".join(f'<li style="margin-bottom: 10px; font-size: 0.9em; line-height: 1.5; color: #aaaacc;">{r}</li>' for r in references)
        refs_html = f"""
        <div style="background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 30px; margin-top: 30px;">
            <h2 style="color: #7b2ff7; font-size: 1.4em; margin-bottom: 18px; padding-bottom: 12px; border-bottom: 1px solid #2a2a4a;">References</h2>
            <ol style="padding-left: 20px; list-style: none;">
                {refs_items}
            </ol>
        </div>"""

    subject_escaped = escape(subject)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeepSearch: {subject_escaped} — {run_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
            background: #0a0a14;
            color: #e0e0e0;
            line-height: 1.6;
        }}

        .container {{
            max-width: 960px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            text-align: center;
            padding: 50px 20px;
            background: linear-gradient(135deg, #0f0f2a 0%, #1a1040 50%, #0a2040 100%);
            border-radius: 16px;
            margin-bottom: 30px;
            border: 1px solid #3a2a6a;
        }}

        header h1 {{
            font-size: 2.6em;
            background: linear-gradient(90deg, #00d2ff, #7b2ff7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }}

        header .subtitle {{
            color: #80a0ff;
            font-size: 1.1em;
            margin-bottom: 5px;
        }}

        header .type-badge {{
            display: inline-block;
            background: linear-gradient(90deg, #7b2ff7, #00d2ff);
            color: white;
            padding: 4px 16px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 15px;
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
            background: linear-gradient(135deg, #12122a 0%, #1a1a3a 100%);
            border: 1px solid #3a3a6a;
            border-radius: 12px;
            padding: 35px 35px;
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
            margin-bottom: 16px;
            color: #ccccdd;
            font-size: 1.02em;
            line-height: 1.8;
        }}

        .editorial p:last-child {{
            margin-bottom: 0;
        }}

        .audio-player {{
            margin-bottom: 20px;
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

        .infographics {{
            margin-bottom: 30px;
        }}

        .source-section {{
            background: #12122a;
            border: 1px solid #2a2a4a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }}

        .source-section:hover {{
            border-color: #7b2ff7;
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

        .paper-count {{
            background: #7b2ff733;
            color: #a66bff;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
        }}

        .paper {{
            padding: 16px 0;
            border-bottom: 1px solid #1e1e38;
        }}

        .paper:last-child {{
            border-bottom: none;
        }}

        .paper h3 {{
            font-size: 1.05em;
            margin-bottom: 4px;
        }}

        .paper h3 a {{
            color: #e0e0e0;
            text-decoration: none;
        }}

        .paper h3 a:hover {{
            color: #00d2ff;
        }}

        .paper .meta {{
            font-size: 0.82em;
            color: #666688;
            margin-bottom: 6px;
        }}

        .paper .abstract {{
            color: #9999bb;
            font-size: 0.9em;
            line-height: 1.5;
        }}

        footer {{
            text-align: center;
            padding: 30px;
            color: #555577;
            font-size: 0.85em;
        }}

        @media (max-width: 600px) {{
            header h1 {{ font-size: 1.8em; }}
            header .stats {{ flex-direction: column; gap: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="type-badge">Deep Research Digest</div>
            <h1>{subject_escaped}</h1>
            <div class="subtitle">{run_date}</div>
            <div class="stats">
                <div class="stat"><strong>{source_count}</strong> academic sources</div>
                <div class="stat"><strong>{total_papers}</strong> papers & articles</div>
            </div>
        </header>

        {f'''<div class="editorial">
            <h2>Research Digest</h2>
            {f'<div class="audio-player"><audio controls><source src="{audio_src}" type="audio/mpeg">Your browser does not support audio.</audio></div>' if audio_src else ''}
            {editorial_html}
        </div>''' if editorial_html else ''}

        {f'<div class="infographics">{infographics_html}</div>' if infographics_html else ''}

        <h2 style="color: #7b2ff7; margin-bottom: 20px; font-size: 1.4em;">Papers & Sources</h2>
"""

    for source_name, data in all_results.items():
        articles = data["articles"]
        site_url = data["site_url"]
        if not articles:
            continue

        papers_html = ""
        for art in articles:
            meta_parts = []
            if art.get("authors"):
                meta_parts.append(art["authors"])
            if art.get("date"):
                meta_parts.append(art["date"])
            if art.get("citations"):
                meta_parts.append(f"{art['citations']} citations")
            meta_str = " | ".join(meta_parts)

            papers_html += f"""
                <div class="paper">
                    <h3><a href="{escape(art['link'])}" target="_blank">{escape(art['title'])}</a></h3>
                    <div class="meta">{escape(meta_str)}</div>
                    <p class="abstract">{escape(art['summary'])}</p>
                </div>"""

        html += f"""
        <div class="source-section">
            <div class="source-header">
                <h2><a href="{escape(site_url)}" target="_blank">{escape(source_name)}</a></h2>
                <span class="paper-count">{len(articles)} paper{"s" if len(articles) != 1 else ""}</span>
            </div>
            {papers_html}
        </div>"""

    html += f"""
        {refs_html}

        <footer>
            Generated on {run_date} by DeepSearch Academic Research Digest
        </footer>
    </div>
</body>
</html>"""

    return html


# --- Email ---

def send_email(html_content, subject, run_date, recipients, audio_bytes=None, audio_filename=None):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        print("[ERROR] GMAIL_APP_PASSWORD environment variable not set.")
        return False

    if not recipients:
        print("[SKIP] No recipients — email not sent.")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"DeepSearch: {subject} — {run_date}"
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)

    alt_part = MIMEMultipart("alternative")
    plain_text = f"DeepSearch: {subject} Research Digest for {run_date}. Open in a browser for the full newsletter."
    alt_part.attach(MIMEText(plain_text, "plain"))

    if audio_bytes:
        email_html = re.sub(
            r'<div class="audio-player">.*?</div>',
            '<p style="color: #80f0e0; font-style: italic; margin-bottom: 14px;">Audio narration of editorial digest attached to this email.</p>',
            html_content, flags=re.DOTALL,
        )
    else:
        email_html = re.sub(r'<div class="audio-player">.*?</div>', '', html_content, flags=re.DOTALL)
    alt_part.attach(MIMEText(email_html, "html", "utf-8"))
    msg.attach(alt_part)

    if audio_bytes and audio_filename:
        audio_part = MIMEBase("audio", "mpeg")
        audio_part.set_payload(audio_bytes)
        encoders.encode_base64(audio_part)
        audio_part.add_header("Content-Disposition", "attachment", filename=audio_filename)
        msg.attach(audio_part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, app_password)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
        print(f"Email sent to {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


# --- Utility ---

def sanitize_filename(subject):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", subject).strip("_")


# --- User Input ---

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
        return None, f"Invalid domain '{domain}'"
    return email, None


def collect_emails():
    print("Enter recipient email addresses (up to 10). Press Enter with no input to finish.")
    print()
    emails = []
    while len(emails) < 10:
        prompt = f"  Email {len(emails) + 1}: "
        entry = input(prompt).strip()
        if not entry:
            break
        validated, error = validate_email(entry)
        if error:
            print(f"    [Invalid] {error}")
            continue
        if validated in emails:
            print(f"    [Duplicate] Already added.")
            continue
        emails.append(validated)
        print(f"    [OK] {validated}")
    return emails


# --- Main ---

def main():
    import argparse

    parser = argparse.ArgumentParser(description="DeepSearch — Academic research digest with neural TTS")
    parser.add_argument("quick_subject", nargs="?", type=str, default=None, help="Subject for quick mode (auto-approved)")
    parser.add_argument("--subject", type=str, help="Subject to research (non-interactive mode)")
    parser.add_argument("--recipients", type=str, help="Comma-separated recipient emails")
    parser.add_argument("--lang", type=str, default="1", help="Audio: 0=none, 1=English, 2=Turkish, 3=French")
    parser.add_argument("--speed", type=str, default="1", help="Audio speed: 1=0.75x (default), 2=1x, 3=1.25x")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    args = parser.parse_args()

    quick_mode = args.quick_subject is not None and args.subject is None
    is_interactive = args.subject is None and not quick_mode

    if quick_mode:
        subject = args.quick_subject
        audio_opt = AUDIO_OPTIONS["1"]
        speed = SPEED_OPTIONS["1"]
        recipients = [EMAIL_TO]
        print("=" * 50)
        print(f"  DeepSearch Quick: \"{subject}\"")
        print(f"  English | 0.75x speed | {EMAIL_TO}")
        print("=" * 50)
    elif is_interactive:
        print("=" * 50)
        print("  DeepSearch — Academic Research Digest")
        print("=" * 50)
        print()

        subject = input("Enter research topic: ").strip()
        if not subject:
            print("No subject provided. Exiting.")
            sys.exit(1)

        print()
        audio_opt = ask_audio()
        if audio_opt["voice"]:
            speed = ask_speed()
        else:
            speed = AUDIO_SPEED
    else:
        subject = args.subject
        audio_opt = AUDIO_OPTIONS.get(args.lang, AUDIO_OPTIONS["1"])
        speed = SPEED_OPTIONS.get(args.speed, SPEED_OPTIONS["1"])

    voice = audio_opt["voice"]

    if not quick_mode:
        if args.recipients:
            recipients = [e.strip() for e in args.recipients.split(",") if e.strip()]
        elif is_interactive:
            print()
            recipients = collect_emails()
            if not recipients:
                print("  No valid emails entered. Digest will be saved but not emailed.")
        else:
            recipients = [EMAIL_TO]

        if is_interactive:
            print()
            print("=" * 50)
            print("  REVIEW")
            print("=" * 50)
            print(f"  Topic:    {subject}")
            print(f"  Audio:    {audio_opt['name']}" + (f" ({speed}x)" if audio_opt["voice"] else ""))
            print(f"  Email:    {', '.join(recipients) if recipients else 'None'}")
            print("=" * 50)
            confirm = input("  Proceed? (y/n): ").strip().lower()
            if confirm not in ("y", "yes"):
                print("\n  Cancelled.")
                sys.exit(0)

    # Fetch academic sources
    run_date = datetime.now().strftime("%Y-%m-%d")
    safe_name = sanitize_filename(subject)
    filename = os.path.join(SCRIPT_DIR, f"DeepSearch_{safe_name}_{run_date}.html")

    print()
    print(f"Topic: {subject}")
    print(f"Date:  {run_date}")
    print("-" * 50)
    print()

    all_results = fetch_all_academic(subject)
    all_results = deduplicate_papers(all_results)

    total = sum(len(d["articles"]) for d in all_results.values())
    print(f"\nTotal papers/articles: {total}")

    # Generate editorial (10 paragraphs, 1000+ words)
    print()
    print("Generating editorial digest (10 paragraphs, 1000+ words)...")
    editorial_html = generate_editorial(all_results, subject, run_date)

    # Generate infographics
    print("Generating infographics...")
    infographics_html = generate_infographics(all_results, subject, run_date)

    # Build references
    references = build_references(all_results)
    print(f"Built {len(references)} references")

    # Generate audio (editorial only)
    print("Generating audio narration of editorial...")
    audio_path = os.path.join(SCRIPT_DIR, f"DeepSearch_{safe_name}_{run_date}.mp3")
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

    # Generate HTML
    print("Generating HTML digest...")
    html = generate_html(all_results, subject, run_date, editorial_html, infographics_html, references, audio_src)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Digest saved: {filename}")

    # Send email
    if not args.no_email and recipients:
        print()
        send_email(html, subject, run_date, recipients, audio_bytes, audio_filename)

    print("\nDone!")


if __name__ == "__main__":
    main()

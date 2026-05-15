# AI Newsletter Generator

## What this project does
A Python script that fetches AI news articles from 10 RSS sources, generates a styled dark-theme HTML newsletter, and emails it to the user via Gmail SMTP. Output files are named `Sites_YYYY-MM-DD.html`.

## Architecture
Single-file script (`ai_newsletter.py`) with no external framework. Uses:
- `feedparser` + `requests` for RSS fetching
- `smtplib` for Gmail SMTP email delivery
- Pure string-based HTML generation (no templating engine)

## 10 News Sources
1. TechCrunch AI
2. The Verge AI
3. Ars Technica (filtered for AI keywords)
4. VentureBeat AI
5. MIT Technology Review (filtered for AI keywords)
6. Wired AI
7. The Register (filtered for AI keywords)
8. Google AI Blog
9. OpenAI Blog
10. Hugging Face Blog

Sources with `filter_keywords` fetch a general feed and filter client-side. The rest use AI-specific RSS endpoints.

## Configuration
- **Email settings** are constants at the top of `ai_newsletter.py` (`EMAIL_FROM`, `EMAIL_TO`, `SMTP_SERVER`, `SMTP_PORT`)
- **Gmail App Password** is read from `GMAIL_APP_PASSWORD` environment variable, stored locally in `.env` (gitignored)
- **MAX_ARTICLES_PER_SOURCE** = 5

## How to run
```bash
source .env && export GMAIL_APP_PASSWORD && python3 ai_newsletter.py
# Or directly:
export GMAIL_APP_PASSWORD="..." && python3 ai_newsletter.py
```

## Daily schedule
A macOS cron job runs daily at 8:00 AM local time. Logs go to `newsletter.log`. View/edit with `crontab -e`.

## Dependencies
```
pip install feedparser requests
```

## Files
- `ai_newsletter.py` — main script
- `.env` — Gmail App Password (gitignored, DO NOT commit)
- `.gitignore` — excludes `.env`, `newsletter.log`, generated HTML files
- `Sites_*.html` — generated newsletters (gitignored)
- `newsletter.log` — cron output log (gitignored)

## GitHub
Repo: https://github.com/Sinus-1971/ai-newsletter

## Known considerations
- Some RSS sources may block requests or change URLs over time — check warnings in output
- Mac must be awake at 8 AM for cron to fire (macOS catches up on missed jobs when it wakes)
- The HTML uses inline CSS for email compatibility

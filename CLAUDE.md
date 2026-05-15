# Newsletter Generator Suite

This repo contains two newsletter generators sharing the same architecture and credentials.

---

## 1. ai_newsletter.py — AI-focused newsletter

Fetches AI news from 10 hardcoded RSS sources (TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Tech Review, Wired, The Register, Google AI Blog, OpenAI Blog, Hugging Face Blog). Generates a Claude API editorial summary and emails a styled HTML newsletter. Output: `Sites_YYYY-MM-DD.html`.

Sources with `filter_keywords` fetch a general feed and filter client-side. The rest use AI-specific RSS endpoints.

## 2. AgentGeneric.py — Any-subject newsletter

Prompts the user for a subject, dynamically builds sources (Google News, Google News recent, Reddit, Bing News, TechCrunch, The Verge, Ars Technica, Wired, Reuters via Google News, BBC via Google News), deduplicates articles, generates a Claude API editorial, and emails the newsletter. Output: `{Subject}_{YYYY-MM-DD}.html`.

**Key differences from ai_newsletter.py:**
- Dynamic source construction via `build_sources(subject)` using Google News RSS `q=` param
- Reddit JSON API fetcher (`fetch_reddit`)
- Cross-source deduplication (`deduplicate_articles`)
- CLI argument support (`--subject`, `--no-email`, `--no-cron`) for non-interactive/cron use
- Self-managing cron: prompts user to schedule, appends tagged cron entries (`# AgentGeneric:{subject}`)
- Shows currently scheduled subjects on startup

## Shared architecture
Both scripts use:
- `feedparser` + `requests` for RSS fetching
- `anthropic` SDK (Claude API, model: `claude-sonnet-4-6`) for editorial summary generation
- `smtplib` for Gmail SMTP email delivery
- Pure string-based HTML generation (no templating engine)

## Newsletter structure (both apps)
1. **Header** — title, date, source/article counts
2. **Editorial Summary** — 5-6 paragraph AI-generated analysis with embedded article links
3. **All Articles by Source** — full article listings grouped by source

## Configuration
- **Email settings** — constants at the top of each script (`EMAIL_FROM`, `EMAIL_TO`)
- **GMAIL_APP_PASSWORD** — environment variable, stored in `.env` (gitignored)
- **ANTHROPIC_API_KEY** — environment variable, stored in `.env` (gitignored)
- **MAX_ARTICLES_PER_SOURCE** = 5

## How to run
```bash
# AI newsletter (non-interactive)
export GMAIL_APP_PASSWORD="..." ANTHROPIC_API_KEY="..." && python3 ai_newsletter.py

# AgentGeneric (interactive — prompts for subject and cron)
export GMAIL_APP_PASSWORD="..." ANTHROPIC_API_KEY="..." && python3 AgentGeneric.py

# AgentGeneric (non-interactive — for cron or scripting)
export GMAIL_APP_PASSWORD="..." ANTHROPIC_API_KEY="..." && python3 AgentGeneric.py --subject "Quantum Computing"
```

## Daily schedule
Cron jobs run daily at 8:00 AM local time. View/edit with `crontab -e`.
- `ai_newsletter.py` — single cron entry, logs to `newsletter.log`
- `AgentGeneric.py` — one cron entry per subject, tagged `# AgentGeneric:{subject}`, logs to `newsletter_{subject}.log`

## Dependencies
```
pip install feedparser requests anthropic
```

## Files
- `ai_newsletter.py` — AI-focused newsletter script
- `AgentGeneric.py` — generic subject newsletter script
- `.env` — Gmail App Password and Anthropic API key (gitignored, DO NOT commit)
- `.gitignore` — excludes `.env`, logs, generated HTML files
- `Sites_*.html` — AI newsletter output (gitignored)
- `{Subject}_*.html` — AgentGeneric output (gitignored)
- `newsletter*.log` — cron output logs (gitignored)

## GitHub
Repo: https://github.com/Sinus-1971/ai-newsletter

## Known considerations
- Some RSS sources may block requests or change URLs over time — check warnings in output
- Mac must be awake at 8 AM for cron to fire (macOS catches up on missed jobs when it wakes)
- The HTML uses inline CSS for email compatibility
- Editorial generation gracefully degrades — if ANTHROPIC_API_KEY is missing, the newsletter still generates without the editorial section
- Claude API costs are minimal (~$0.01 per run using claude-sonnet-4-6)
- AgentGeneric's filtered sources (TechCrunch, Wired, etc.) may return 0 results for niche subjects — Google News and Bing News are the primary sources for any topic

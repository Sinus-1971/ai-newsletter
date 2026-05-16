# Newsletter Generator Suite

This repo contains two newsletter generators and a watchdog, sharing the same architecture and credentials.
Can be run from any directory — all paths resolve relative to the script location.

---

## 1. ai_newsletter.py — AI-focused newsletter

Fetches AI news from 10 hardcoded RSS sources (TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Tech Review, Wired, The Register, Google AI Blog, OpenAI Blog, Hugging Face Blog). Generates a Claude API editorial summary with audio narration (English, 1.25x speed, macOS TTS) and emails a styled HTML newsletter. Audio is compressed via `afconvert` (64 kbps AAC) and embedded as base64 data URI in the HTML for self-contained playback. Output: `Sites_YYYY-MM-DD.html`.

Sources with `filter_keywords` fetch a general feed and filter client-side. The rest use AI-specific RSS endpoints.

## 2. AgentGeneric.py — Any-subject newsletter

Full interactive application with the following startup flow:

1. **Cron job management** — lists all scheduled newsletters (AI Newsletter + AgentGeneric) with type, subject, schedule, recipients. User can select jobs by number to remove, with confirmation
2. **Subject input** — any topic (e.g., "Quantum Computing", "Cybersecurity", "Whiskey")
3. **Audio selection** — 0: No audio, 1: English (default), 2: Turkish, 3: French. Speed: 1.25x
4. **Email collection** — up to 10 recipients with validation (missing @, no domain, invalid TLD, duplicates)
5. **Source discovery** — Claude API identifies 10 best authoritative sites, cached for 7 days in `.source_cache/`. Use `--refresh-sources` to force rediscovery
6. **RSS resolution** — 3-tier: AI-suggested URL → pattern discovery (`/feed/`, `/rss`, `/rss.xml`, etc.) → Google News site filter
7. **Article fetching** — from discovered sites + Google News + Reddit, with deduplication
8. **Editorial generation** — Claude API writes 5-6 paragraphs in the selected language with embedded article links
9. **Audio narration** — macOS `say` generates .m4a at 1.25x speed, compressed via `afconvert` (64 kbps AAC), embedded as base64 data URI in HTML. Voices: Samantha/English, Yelda/Turkish, Thomas/French
10. **HTML generation** — dark theme with turquoise header, self-contained audio player (base64), editorial section, article listings by source
11. **Schedule prompt** — daily or weekly, custom time (HH:MM), day of week for weekly
12. **Confirmation summary** — displays subject, language, article count, recipients, schedule. Requires y/n approval
13. **Send & schedule** — sends email immediately, sets up cron if periodic (first send acts as test run)

**Key technical features:**
- `SCRIPT_DIR` — all paths resolve from script location, runnable from any directory
- `discover_best_sites(subject)` — Claude API returning JSON array of 10 sites
- Source caching in `.source_cache/{subject}_sources.json` — expires after 7 days
- `validate_email()` — checks @, domain, TLD, duplicates
- `display_and_manage_jobs()` — parses crontab, shows all newsletter jobs, offers numbered removal
- `generate_audio()` — macOS `say` with 1.25x speed, compressed via `afconvert`, language-specific voice
- `audio_to_data_uri()` — reads .m4a, returns base64 data URI for HTML embedding; .m4a deleted after embedding
- CLI: `--subject`, `--recipients`, `--lang` (0/1/2/3), `--no-email`, `--refresh-sources`
- Cron entries tagged `# AgentGeneric:{subject}` for identification and management

## 3. newsletter_watchdog.py — Missed-job recovery

Runs hourly via cron. Parses crontab for all newsletter jobs (ai_newsletter + AgentGeneric), checks if each job's expected output file exists for today, and re-runs any missed job.

**Logic:**
- For daily jobs: checks every day
- For weekly jobs: checks only on the scheduled day of week
- Only triggers if current time is past the job's scheduled time AND today's output file is missing
- Runs the exact cron command, inheriting environment from `.env`
- Tagged `# NewsletterWatchdog` in crontab

**Output files checked:**
- `ai_newsletter.py` → `Sites_{YYYY-MM-DD}.html`
- `AgentGeneric.py` → `{Subject}_{YYYY-MM-DD}.html`

## Shared architecture
Both scripts use:
- `feedparser` + `requests` for RSS fetching
- `anthropic` SDK (Claude API, model: `claude-sonnet-4-6`) for editorial summary generation
- `smtplib` for Gmail SMTP email delivery
- macOS `say` + `afconvert` for TTS audio narration (compressed .m4a, 1.25x speed, base64-embedded in HTML)
- `python-dotenv` for auto-loading `.env` credentials
- `SCRIPT_DIR` constant for directory-independent operation
- Pure string-based HTML generation (no templating engine)

## Newsletter structure (both apps)
1. **Header** — turquoise title, date, source/article counts
2. **Editorial Summary** — embedded audio player + 5-6 paragraph AI-generated analysis with embedded article links
3. **All Articles by Source** — full article listings grouped by source (title, date, summary, link)

## Configuration
- **Email settings** — constants at top of each script (`EMAIL_FROM`, `EMAIL_TO`)
- **GMAIL_APP_PASSWORD** — environment variable, auto-loaded from `.env`
- **ANTHROPIC_API_KEY** — environment variable, auto-loaded from `.env`
- Both vars also set in `~/.zshrc` for shell-level access
- **MAX_ARTICLES_PER_SOURCE** = 5
- **AUDIO_SPEED** = 1.25 (250 words/min)
- **CACHE_MAX_AGE_DAYS** = 7

## How to run
```bash
# AI newsletter (can run from any directory)
python3 /path/to/ai_newsletter.py

# AgentGeneric (interactive — full menu flow)
python3 /path/to/AgentGeneric.py

# AgentGeneric (non-interactive — for cron or scripting)
python3 /path/to/AgentGeneric.py --subject "Quantum Computing" --recipients "a@b.com" --lang 2
```

## Audio options (AgentGeneric)
- `--lang 0` — No audio
- `--lang 1` — English (Samantha voice) — default
- `--lang 2` — Turkish (Yelda voice)
- `--lang 3` — French (Thomas voice)

## Schedule & watchdog
Cron jobs are user-configurable (daily or weekly, any time). View/edit with `crontab -e`.
- `ai_newsletter.py` — single cron entry at 8:00 AM, logs to `newsletter.log`
- `AgentGeneric.py` — one cron entry per subject, tagged `# AgentGeneric:{subject}`, logs to `newsletter_{subject}.log`
- `newsletter_watchdog.py` — runs hourly at :00, tagged `# NewsletterWatchdog`, logs to `newsletter_watchdog.log`
- AgentGeneric shows and manages all cron jobs (including watchdog) on startup

## Dependencies
```
pip install feedparser requests anthropic python-dotenv
```

## Files
- `ai_newsletter.py` — AI-focused newsletter script
- `AgentGeneric.py` — generic subject newsletter script (interactive + CLI)
- `newsletter_watchdog.py` — hourly missed-job recovery script
- `.env` — Gmail App Password and Anthropic API key (gitignored, DO NOT commit)
- `.gitignore` — excludes `.env`, logs, generated HTML/audio files, cache
- `.source_cache/` — cached source discovery results per subject (gitignored)
- `Sites_*.html` — AI newsletter output (gitignored)
- `{Subject}_*.html` — AgentGeneric output (gitignored)
- `newsletter*.log` — cron output logs (gitignored)

## GitHub
Repo: https://github.com/Sinus-1971/ai-newsletter (account: Sinus-1971)

## Known considerations
- Some RSS sources may block requests or change URLs over time — check warnings in output
- Mac must be awake for cron to fire; the hourly watchdog recovers missed jobs when the Mac wakes up
- The HTML uses inline CSS for email compatibility
- Editorial and audio gracefully degrade — if API key missing or call fails, newsletter still generates without them
- Claude API costs are minimal (~$0.01-0.02 per run using claude-sonnet-4-6; source discovery cached to reduce calls)
- Audio uses macOS `say` + `afconvert` — only works on macOS, not Linux/cloud servers
- Audio is compressed (64 kbps AAC) and embedded as base64 in HTML; .m4a files are deleted after embedding
- Source cache expires after 7 days; use `--refresh-sources` to force rediscovery

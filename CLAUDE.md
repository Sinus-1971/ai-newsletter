# Newsletter Generator Suite

This repo contains two newsletter generators and a watchdog, sharing the same architecture and credentials.
Can be run from any directory — all paths resolve relative to the script location.

**Claude Session ID:** `ccb25ceb-ca22-4c85-851f-3c1a201be811`

---

## 1. ai_newsletter.py — AI-focused newsletter

Fetches AI news from 10 hardcoded RSS sources (TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Tech Review, Wired, The Register, Google AI Blog, OpenAI Blog, Hugging Face Blog). Generates a Claude API editorial summary (max_tokens=4000) with audio narration (English, 1.25x speed, macOS TTS). Audio is compressed via `afconvert` (64 kbps AAC), embedded as base64 in local HTML, and attached as `.m4a` to email. Output: `Sites_YYYY-MM-DD.html`.

Sources with `filter_keywords` fetch a general feed and filter client-side. The rest use AI-specific RSS endpoints.

## 2. AgentGeneric.py — Any-subject newsletter

Full interactive application. All user input is collected upfront, reviewed, and confirmed before processing begins:

1. **Cron job management** — lists all scheduled newsletters (AI Newsletter + AgentGeneric + Watchdog) with type, subject, schedule, recipients. User can select jobs by number to remove, with confirmation
2. **Subject input** — any topic (e.g., "Quantum Computing", "Cybersecurity", "Whiskey")
3. **Audio selection** — 0: No audio, 1: English (default), 2: Turkish, 3: French. Speed: 1.25x
4. **Email collection** — up to 10 recipients with validation (missing @, no domain, invalid TLD, duplicates)
5. **Schedule prompt** — daily or weekly, custom time (HH:MM), day of week for weekly
6. **Review approval** — displays subject, language, audio, recipients, schedule. Requires y/n before processing starts
7. **Source discovery** — Claude API identifies 10 best authoritative sites, cached for 7 days in `.source_cache/`. Use `--refresh-sources` to force rediscovery
8. **RSS resolution** — 3-tier: AI-suggested URL → pattern discovery (`/feed/`, `/rss`, `/rss.xml`, etc.) → Google News site filter
9. **Article fetching** — from discovered sites + Google News + Reddit, with deduplication
10. **Editorial generation** — Claude API (max_tokens=4000) writes 5-6 paragraphs in the selected language with embedded article links. Warns if output was truncated via stop_reason check
11. **Audio narration** — macOS `say` generates .m4a at 1.25x speed, compressed via `afconvert` (64 kbps AAC). Voices: Samantha/English, Yelda/Turkish, Thomas/French
12. **HTML generation** — dark theme with turquoise header, self-contained audio player (base64 in local file), editorial section, article listings by source
13. **Email delivery** — `multipart/mixed` email: lightweight HTML body (audio stripped, replaced with "Audio narration attached" note) + `.m4a` audio as MIME attachment. Sets up cron if periodic

**Key technical features:**
- `SCRIPT_DIR` — all paths resolve from script location, runnable from any directory
- `discover_best_sites(subject)` — Claude API returning JSON array of 10 sites
- Source caching in `.source_cache/{subject}_sources.json` — expires after 7 days
- `validate_email()` — checks @, domain, TLD, duplicates
- `display_and_manage_jobs()` — parses crontab, shows all newsletter jobs (including watchdog), offers numbered removal
- `generate_audio()` — macOS `say` with 1.25x speed, compressed via `afconvert` (64 kbps AAC)
- `audio_to_data_uri()` — converts audio bytes to base64 data URI for local HTML embedding
- `send_email()` — `multipart/mixed` with `multipart/alternative` body + audio MIME attachment; base64 audio stripped from HTML to stay under Gmail's ~102 KB rendering limit
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
- `anthropic` SDK (Claude API, model: `claude-sonnet-4-6`, max_tokens=4000) for editorial summary generation
- `smtplib` for Gmail SMTP email delivery (`multipart/mixed` with audio attachment)
- macOS `say` + `afconvert` for TTS audio (compressed 64 kbps AAC .m4a)
- `python-dotenv` for auto-loading `.env` credentials
- `SCRIPT_DIR` constant for directory-independent operation
- Pure string-based HTML generation (no templating engine)

## Audio pipeline (both apps)
1. `generate_audio()` — macOS `say` creates .m4a, `afconvert` compresses to 64 kbps AAC
2. `audio_to_data_uri()` — reads compressed .m4a bytes, returns base64 data URI
3. Local HTML — audio embedded as base64 data URI in `<audio>` tag (self-contained playback)
4. Email — base64 audio stripped from HTML body (Gmail's ~102 KB limit), `.m4a` attached as MIME part
5. Cleanup — .m4a file deleted from disk after embedding + attachment prepared

## Newsletter structure (both apps)
1. **Header** — turquoise title, date, source/article counts
2. **Editorial Summary** — audio player (base64 in local file) + 5-6 paragraph AI-generated analysis with embedded article links
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
- `AgentGenericClaudeSessionID.txt` — Claude Code session ID for continuity
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
- Editorial uses max_tokens=4000 with stop_reason check; warns if output was truncated
- Claude API costs are minimal (~$0.01-0.02 per run using claude-sonnet-4-6; source discovery cached to reduce calls)
- Audio uses macOS `say` + `afconvert` — only works on macOS, not Linux/cloud servers
- Audio: base64-embedded in local HTML for self-contained playback; attached as .m4a in email (stripped from HTML to stay under Gmail's ~102 KB limit)
- Source cache expires after 7 days; use `--refresh-sources` to force rediscovery

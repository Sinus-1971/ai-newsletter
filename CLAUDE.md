# Newsletter Generator Suite

This repo contains three newsletter generators and a watchdog, sharing the same architecture and credentials.
Can be run from any directory — all paths resolve relative to the script location.

**Claude Session ID:** `741e6828-33d9-497c-88a6-52f3521b9aa1`

---

## 1. ai_newsletter.py — AI-focused newsletter

Fetches AI news from 10 hardcoded RSS sources (TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Tech Review, Wired, The Register, Google AI Blog, OpenAI Blog, Hugging Face Blog). Generates a Claude API editorial summary (max_tokens=4000) with audio narration (English, 1.25x speed, macOS TTS). Audio is compressed via `afconvert` (64 kbps AAC), embedded as base64 in local HTML, and attached as `.m4a` to email. Output: `Sites_YYYY-MM-DD.html`.

Sources with `filter_keywords` fetch a general feed and filter client-side. The rest use AI-specific RSS endpoints.

## 2. AgentGeneric.py — Any-subject newsletter

Full interactive application. All user input is collected upfront, reviewed, and confirmed before processing begins:

1. **Cron job management** — lists all scheduled newsletters (AI Newsletter + AgentGeneric + Watchdog) with type, subject, schedule, recipients. User can select jobs by number to remove, with confirmation
2. **Subject input** — any topic (e.g., "Quantum Computing", "Cybersecurity", "Whiskey")
3. **Audio selection** — 0: No audio, 1: English (default), 2: Turkish, 3: French
4. **Speed selection** — 0.75x (slow), 1x (normal, default), 1.25x (fast)
5. **Duration selection** — narration length in minutes (1-30, default 3). Editorial scales accordingly
6. **Email collection** — up to 10 recipients with validation (missing @, no domain, invalid TLD, duplicates)
7. **Schedule prompt** — daily or weekly, custom time (HH:MM), day of week for weekly
8. **Review approval** — displays subject, language, audio, speed, duration, recipients, schedule. Requires y/n before processing starts
9. **Source discovery** — Claude API identifies 10 best authoritative sites, cached for 7 days in `.source_cache/`. Use `--refresh-sources` to force rediscovery
10. **RSS resolution** — 3-tier: AI-suggested URL → pattern discovery (`/feed/`, `/rss`, `/rss.xml`, etc.) → Google News site filter
11. **Article fetching** — from discovered sites + Google News + Reddit, with deduplication
12. **Editorial generation** — Claude API writes editorial scaled to target duration (word count = duration × 200 × speed). max_tokens scales automatically. Warns if output was truncated via stop_reason check
13. **Audio narration** — macOS `say` generates .m4a at selected speed, compressed via `afconvert` (64 kbps AAC). Voices: Samantha/English, Yelda/Turkish, Thomas/French
14. **HTML generation** — dark theme with turquoise header, self-contained audio player (base64 in local file), editorial section, article listings by source
15. **Email delivery** — `multipart/mixed` email: lightweight HTML body (audio stripped, replaced with "Audio narration attached" note) + `.m4a` audio as MIME attachment. Sets up cron if periodic

**Key technical features:**
- `SCRIPT_DIR` — all paths resolve from script location, runnable from any directory
- `discover_best_sites(subject)` — Claude API returning JSON array of 10 sites
- Source caching in `.source_cache/{subject}_sources.json` — expires after 7 days
- `validate_email()` — checks @, domain, TLD, duplicates
- `display_and_manage_jobs()` — parses crontab, shows all newsletter jobs (including watchdog), offers numbered removal
- `generate_audio()` — macOS `say` with 1.25x speed, compressed via `afconvert` (64 kbps AAC)
- `audio_to_data_uri()` — converts audio bytes to base64 data URI for local HTML embedding
- `send_email()` — `multipart/mixed` with `multipart/alternative` body + audio MIME attachment; base64 audio stripped from HTML to stay under Gmail's ~102 KB rendering limit
- Quick mode: `python3 AgentGeneric.py "Subject"` — auto-approved with English, 0.75x speed, 3 min, emailed to default recipient
- CLI: `--subject`, `--recipients`, `--lang` (0/1/2/3), `--speed` (1/2/3), `--duration` (1-30), `--no-email`, `--refresh-sources`
- Cron entries tagged `# AgentGeneric:{subject}` for identification and management

## 3. Magent.py — Microsoft neural TTS variant of AgentGeneric

Same functionality as AgentGeneric.py but uses **Microsoft Edge neural TTS** (`edge-tts`) instead of macOS `say`. Produces natural-sounding narration via `speech.platform.bing.com` — free, no API key, no account needed.

**Differences from AgentGeneric.py:**
- Audio engine: `edge-tts` (async, internet-required) instead of macOS `say` + `afconvert`
- Voices: `en-US-AriaNeural` (English), `tr-TR-EmelNeural` (Turkish), `fr-FR-DeniseNeural` (French)
- Output format: `.mp3` instead of `.m4a`
- Platform-independent — works on macOS, Linux, Windows (not macOS-only)
- Cron entries tagged `# Magent:{subject}`

## 4. newsletter_watchdog.py — Missed-job recovery

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
All scripts use:
- `feedparser` + `requests` for RSS fetching
- `anthropic` SDK (Claude API, model: `claude-sonnet-4-6`) for editorial summary generation
- `smtplib` for Gmail SMTP email delivery (`multipart/mixed` with audio attachment)
- `python-dotenv` for auto-loading `.env` credentials
- `SCRIPT_DIR` constant for directory-independent operation
- Pure string-based HTML generation (no templating engine)

## Audio pipeline
**ai_newsletter.py & AgentGeneric.py** (macOS-only):
1. `generate_audio()` — macOS `say` creates .m4a, `afconvert` compresses to 64 kbps AAC
2. Local HTML: audio embedded as base64 data URI, email: `.m4a` attached as MIME part

**Magent.py** (cross-platform):
1. `generate_audio()` — `edge-tts` async call to Microsoft speech service, outputs .mp3
2. Local HTML: audio embedded as base64 data URI, email: `.mp3` attached as MIME part

Both: audio stripped from email HTML (Gmail ~102 KB limit), file deleted after embedding + attachment

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
- **AUDIO_SPEED** = selectable: 0.75x (slow), 1x (normal/default), 1.25x (fast)
- **NARRATION_DURATION** = selectable: 1-30 minutes (default 3). Editorial word count scales with duration × speed
- **CACHE_MAX_AGE_DAYS** = 7

## How to run
```bash
# AI newsletter (can run from any directory)
python3 /path/to/ai_newsletter.py

# AgentGeneric — Quick mode (auto-approved: English, 0.75x speed, 3 min, emailed to default recipient)
python3 /path/to/AgentGeneric.py "Philosophy"

# AgentGeneric (interactive — full menu flow)
python3 /path/to/AgentGeneric.py

# AgentGeneric (non-interactive — for cron or scripting)
python3 /path/to/AgentGeneric.py --subject "Quantum Computing" --recipients "a@b.com" --lang 2 --speed 1 --duration 5
```

## Automator / double-click launcher
To run AgentGeneric as a macOS app (double-click), create an Automator Application with a **Run AppleScript** action:
```applescript
on run {input, parameters}
    tell application "Terminal"
        activate
        do script "cd /Users/sinan/projects/Orchestrator/files2 && /opt/anaconda3/bin/python3 AgentGeneric.py"
    end tell
    return input
end run
```
- Must use `/opt/anaconda3/bin/python3` — system python3 lacks feedparser and other dependencies
- Must open Terminal (not "Run Shell Script") because AgentGeneric needs interactive input

## Audio options (AgentGeneric & Magent)
- `--lang 0` — No audio
- `--lang 1` — English (AgentGeneric: Samantha, Magent: AriaNeural) — default
- `--lang 2` — Turkish (AgentGeneric: Yelda, Magent: EmelNeural)
- `--lang 3` — French (AgentGeneric: Thomas, Magent: DeniseNeural)
- `--speed 1` — 0.75x (slow), `--speed 2` — 1x (normal, default), `--speed 3` — 1.25x (fast)
- `--duration N` — narration duration in minutes (1-30, default: 3)

## Schedule & watchdog
Cron jobs are user-configurable (daily or weekly, any time). View/edit with `crontab -e`.
- `ai_newsletter.py` — single cron entry at 8:00 AM, logs to `newsletter.log`
- `AgentGeneric.py` / `Magent.py` — one cron entry per subject, tagged `# AgentGeneric:{subject}` or `# Magent:{subject}`, logs to `newsletter_{subject}.log`
- `newsletter_watchdog.py` — runs hourly at :00, tagged `# NewsletterWatchdog`, logs to `newsletter_watchdog.log`
- AgentGeneric shows and manages all cron jobs (including watchdog) on startup

## Dependencies
```
pip install feedparser requests anthropic python-dotenv edge-tts
```

## Files
- `ai_newsletter.py` — AI-focused newsletter script
- `AgentGeneric.py` — generic subject newsletter script (macOS TTS, interactive + CLI)
- `Magent.py` — generic subject newsletter script (Microsoft neural TTS, interactive + CLI)
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
- Editorial uses dynamic max_tokens (scales with duration) with stop_reason check; warns if output was truncated
- Claude API costs are minimal (~$0.01-0.02 per run using claude-sonnet-4-6; source discovery cached to reduce calls)
- Audio (AgentGeneric): macOS `say` + `afconvert` — only works on macOS
- Audio (Magent): `edge-tts` via Microsoft speech service — cross-platform, requires internet, no API key
- Audio: base64-embedded in local HTML for self-contained playback; attached in email (stripped from HTML to stay under Gmail's ~102 KB limit)
- Source cache expires after 7 days; use `--refresh-sources` to force rediscovery

#!/usr/bin/env python3
"""
Newsletter Watchdog — runs hourly via cron to detect and recover missed newsletter jobs.
Parses crontab for all newsletter entries, checks if today's output exists,
and re-runs any job that should have fired but didn't.
"""

import os
import re
import subprocess
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))


def sanitize_filename(subject):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", subject).strip("_")


def parse_cron_jobs():
    jobs = []
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return jobs
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "newsletter_watchdog.py" in line:
                continue

            parts = line.split()
            if len(parts) < 6:
                continue

            minute, hour = parts[0], parts[1]
            dow = parts[4]

            # Extract command (everything after the 5 cron fields)
            m = re.match(r"^\s*\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(.+)$", line)
            if not m:
                continue
            command = m.group(1)

            marker_match = re.search(r"# AgentGeneric:(.+)$", line)
            if marker_match:
                subject_safe = marker_match.group(1)
                subject_match = re.search(r'--subject\s+"([^"]+)"', line)
                subject = subject_match.group(1) if subject_match else subject_safe.replace("_", " ")
                safe = sanitize_filename(subject)
                jobs.append({
                    "type": "AgentGeneric",
                    "subject": subject,
                    "safe_name": safe,
                    "hour": int(hour),
                    "minute": int(minute),
                    "dow": dow,
                    "output_pattern": f"{safe}_{{date}}.html",
                    "command": command,
                })
            elif "ai_newsletter.py" in line:
                jobs.append({
                    "type": "AI Newsletter",
                    "subject": "AI",
                    "safe_name": "Sites",
                    "hour": int(hour),
                    "minute": int(minute),
                    "dow": dow,
                    "output_pattern": "Sites_{date}.html",
                    "command": command,
                })
    except Exception as e:
        print(f"[ERROR] Failed to parse crontab: {e}")
    return jobs


def should_have_run(job, now):
    if job["dow"] != "*":
        scheduled_dow = int(job["dow"])
        current_dow_cron = (now.weekday() + 1) % 7
        if scheduled_dow != current_dow_cron:
            return False
    scheduled_minutes = job["hour"] * 60 + job["minute"]
    current_minutes = now.hour * 60 + now.minute
    return current_minutes >= scheduled_minutes


def output_exists(job, today_str):
    filename = job["output_pattern"].format(date=today_str)
    return os.path.exists(os.path.join(SCRIPT_DIR, filename))


def run_missed_job(job):
    command = job["command"]
    # Strip log redirect so we can capture output
    cmd_clean = re.sub(r"\s*>>.*$", "", command)
    print(f"  Executing: {cmd_clean[:120]}...")
    try:
        env = os.environ.copy()
        result = subprocess.run(
            command,
            shell=True,
            env=env,
            cwd=SCRIPT_DIR,
            timeout=600,
        )
        if result.returncode == 0:
            print(f"  [OK] Completed successfully")
            return True
        else:
            print(f"  [ERROR] Exit code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] Timed out after 600s")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main():
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    print(f"Newsletter Watchdog — {now.strftime('%Y-%m-%d %H:%M')}")
    print("-" * 40)

    jobs = parse_cron_jobs()
    if not jobs:
        print("No newsletter jobs found in crontab.")
        return

    missed = 0
    recovered = 0

    for job in jobs:
        due = should_have_run(job, now)
        exists = output_exists(job, today_str)

        if exists:
            status = "OK"
        elif due:
            status = "MISSED"
        else:
            status = "pending"

        print(f"  [{status:7s}] {job['type']}: {job['subject']} ({job['hour']:02d}:{job['minute']:02d})")

        if due and not exists:
            missed += 1
            print(f"  -> Output missing, running now...")
            if run_missed_job(job):
                recovered += 1

    print("-" * 40)
    print(f"Jobs: {len(jobs)} | Missed: {missed} | Recovered: {recovered}")


if __name__ == "__main__":
    main()

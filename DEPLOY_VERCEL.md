# Deploying TuitionPe to Vercel

Vercel runs the app as serverless functions — it never "sleeps" like
Render's free tier, but it also has no persistent disk or long-lived
process. The codebase handles this automatically when the `VERCEL` env
var is present (Vercel sets it for you).

## 1. Create a free Postgres database (required)

SQLite cannot work on Vercel (read-only filesystem). Create a free DB at
[neon.tech](https://neon.tech) (recommended — the app already handles
Neon's SSL quirks) and copy the connection string, e.g.
`postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`.

Tables and columns are created/migrated automatically on first boot.

## 2. Import the repo on Vercel

1. Sign in at [vercel.com](https://vercel.com) (use "Continue with GitHub").
2. **Add New → Project** → import `Ankit007jm/Tuitionpe`.
3. Pick the branch (`phase-1`, or `main` after merging the PR).
   Framework preset: **Other**. No build command needed —
   `vercel.json` + `api/index.py` handle everything.

## 3. Set environment variables (Project → Settings → Environment Variables)

| Variable | Required | Value |
|---|---|---|
| `DATABASE_URL` | **yes** | the Neon connection string |
| `SECRET_KEY` | **yes** | long random string (e.g. `python -c "import secrets;print(secrets.token_hex(32))"`) |
| `FORCE_SECURE_COOKIES` | **yes** | `1` (enables Secure cookies + HSTS) |
| `CRON_SECRET` | recommended | random string; Vercel Cron sends it automatically as a Bearer token |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_DEFAULT_SENDER` | for emails | same values as your `.env` |
| `CLOUDINARY_URL` | for image uploads | from cloudinary.com (free tier) — without it, profile/QR uploads fail on Vercel |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | for Google login | add `https://<project>.vercel.app/login/google/callback` as an authorized redirect URI |

Deploy. Done — the app stays warm-ish and never spin-down-sleeps.

## What changes on Vercel (handled in code)

- **Reminder scheduler**: no background threads. The daily summary email
  runs via Vercel Cron (`/cron/daily-reminders`, 01:30 UTC = 07:00 IST,
  configured in `vercel.json`).
- **30-min class alerts**: Vercel's free (Hobby) plan only allows daily
  crons. To keep class alerts, create a free monitor at
  [cron-job.org](https://cron-job.org) hitting
  `https://<project>.vercel.app/cron/class-alerts` every 5 minutes with
  header `Authorization: Bearer <CRON_SECRET>`.
- **Emails** (receipts, notifications) are sent synchronously instead of
  in background threads — requests that send email take a moment longer.
- **Password-reset OTPs** are stored in Postgres, so the flow works
  across serverless invocations.
- **Login rate limiting** is in-memory per instance, so it is weaker on
  serverless (each cold instance starts fresh). CSRF + hashed passwords
  still apply.

## Alternative: keep Render but stop the spin-down

If you ever want to go back: a free [UptimeRobot](https://uptimerobot.com)
or cron-job.org monitor pinging your Render URL every 10 minutes keeps
the free instance awake (Render's 750 free hours/month cover a single
always-on service).

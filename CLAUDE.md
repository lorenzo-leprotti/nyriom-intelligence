# Nyriom Intelligence

**Stack:** Python + Flask + Jinja2 + Tailwind CSS (CDN + typography plugin) + Supabase + Perplexity AI
**Deployment:** Vercel (Root Directory: `.`, Production Branch: `main`)
**Live URL:** https://nyriom-intel-hub.vercel.app

## Architecture

- `main.py` — Flask app with all routes, auth middleware, CSRF protection, CSP headers
- `services/perplexity_service.py` — Two-pass AI pipeline (sonar → sonar-pro) for event summaries and intelligence reports. Includes nh3 HTML sanitization.
- `templates/` — Jinja2 templates (base, home, login, index/dashboard, events, event_detail, archive, report_view, admin, upload_events, offline)
- `templates/base.html` — Shared layout, bottom nav, Tailwind v4 play CDN (`cdn.tailwindcss.com`) with `@plugin "@tailwindcss/typography"` in a `<style type="text/tailwindcss">` block, CSRF meta tag, NyriomDropdown shared JS utility
- `templates/index.html` — Dashboard with Jinja macro `vertical_section()` for vertical sections; custom dropdown selector with color dots; two-column layout (headlines sidebar + inline full report) on desktop, stacked on mobile
- `templates/events.html` — Event listing with custom industry dropdown + time filter pills; pagination
- `templates/archive.html` — Historical report archive with custom dropdowns for vertical and timeframe filters
- `templates/report_view.html` — Standalone printable report page (editorial layout with print styles)
- `static/service-worker.js` — PWA caching (cache name: nyriom-intel-v6)
- `data/sample_events.csv` — 36 industry events across 4 verticals
- `scripts/seed_data.py` — Wipes Supabase tables, seeds events from CSV
- `scripts/generate_summaries.py` — Generates AI summaries for past events (bypasses Flask, calls Perplexity directly)
- `scripts/generate_intelligence_reports.py` — Generates intelligence reports for all 4 verticals (current + backdated)
- `scripts/delete_and_regenerate_reports.py` — Wipes all intelligence reports from Supabase
- `scripts/add_events.py` — Targeted event insert (no wipe), skips duplicates
- `.github/workflows/weekly-intelligence.yml` — Monday 8am UTC cron for auto-generating intelligence reports

## Shared Frontend Components

- **NyriomDropdown** — Reusable dropdown utility in `base.html`. Provides `toggle()`, `close()`, and `init()` methods. Used by dashboard vertical selector, events industry filter, and archive filters. Handles outside-click dismissal and Escape key.

## Verticals

Aerospace, Automotive, Robotics, AI/Electronics

## Auth

- Demo login: `DEMO_PASSWORD` env var (default: `demo2026`)
- Guest access (no credentials)
- Admin panel: `ADMIN_SECRET` env var (default: `admin2026`)

## Key Routes

- `/` — Home page
- `/dashboard` — Intelligence dashboard (4 verticals, custom dropdown selector, two-column editorial layout: sticky headlines sidebar + full report)
- `/events` — Event listing with filters (upcoming/past/3months + industry dropdown)
- `/events/<id>` — Event detail + AI summary
- `/report/<id>` — Printable intelligence report view
- `/archive` — Historical report archive with vertical + timeframe filters
- `/admin` — Admin panel (summary generation, CSV upload)
- `/upload-events` — CSV event upload (admin only)
- `/offline` — PWA offline fallback

## Supabase Tables

- `events` — id, name, industry, start_date, end_date, location, country, website, description
- `event_summaries` — event_id (FK), summary_text, status (completed/failed)
- `intelligence_reports` — vertical, report_html, top_3_json, created_at
- `app_config` — key/value store (app_version)

## Local Development

- Run: `python -c "from dotenv import load_dotenv; load_dotenv(); from main import app; app.run(host='0.0.0.0', port=5001)"`
- Port 5000 blocked by macOS AirPlay — always use port 5001
- `SESSION_COOKIE_SECURE=True` means session cookies don't work on HTTP localhost for admin API calls — use `scripts/generate_summaries.py` instead

## Security

- **HTML Sanitization:** All AI-generated HTML sanitized via `nh3` (allowlisted tags/attributes). Applied in `_clean_html_response()`, `get_latest_report()`, and `view_report()`. `sanitize_html()` is exported from `perplexity_service.py`.
- **CSRF:** `flask-wtf` `CSRFProtect` on all POST endpoints. Hidden `csrf_token` in all forms, `X-CSRFToken` header in fetch calls, meta tag in `base.html`. `/api/version` exempted (GET-only).
- **CSP Header:** Restrictive policy with `'unsafe-inline'` for scripts (Tailwind CDN requirement). Includes `frame-ancestors 'none'`, `form-action 'self'`, `connect-src 'self'`.
- **Input Validation:** Page parameter wrapped in try/except with clamp to >= 1.

## Color Scheme (Warm Editorial)

- Background: stone-50 (`#fafaf9`)
- Card bg: white with stone-200 border
- Text: stone-900 primary, stone-500 secondary
- Accent: blue-700 (`#1d4ed8`)
- Industry tag colors: Aerospace `#2563eb`, Automotive `#0e7490`, Robotics `#ea580c`, AI/Electronics `#0d9488`

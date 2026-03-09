# Nyriom Intelligence

AI-powered market intelligence platform for a cross-industry advanced materials startup. Tracks industry events across 4 verticals, auto-generates post-event summaries using a two-pass AI research pipeline, and delivers weekly intelligence reports through an editorial-style dashboard.

**Live demo:** [nyriom-intel-hub.vercel.app](https://nyriom-intel-hub.vercel.app)

![Intelligence Dashboard — Aerospace vertical](docs/screenshots/dashboard-aerospace.png)

## The Problem

Small B2B commercial teams need to monitor events, regulations, and market signals across multiple industries — but lack the tools and bandwidth to do it systematically. A 4-person team covering Aerospace, Automotive, Robotics, and AI/Electronics can't attend every trade show or read every industry publication.

## The Solution

A mobile-first intelligence hub that:
- Tracks 36 industry events across 4 verticals
- Auto-generates AI-powered post-event summaries using a two-pass research system
- Produces weekly intelligence reports with top headlines and full analysis
- Serves everything through a responsive, editorial-style interface

## How It Works

### Two-Pass AI Pipeline
Every piece of intelligence goes through two sequential Perplexity API calls:

1. **Research pass** (`sonar`): Gathers raw facts — attendees, announcements, themes, market signals
2. **Analysis pass** (`sonar-pro`): Produces structured business intelligence with key takeaways, opportunity analysis, and actionable recommendations

This architecture applies to both event summaries and weekly intelligence reports.

### Intelligence Dashboard
Four vertical-specific reports with a two-column editorial layout: sticky headlines sidebar linking to sources, plus inline full-length analysis. Reports regenerate weekly via GitHub Actions.

### Event Tracker
Browse upcoming and past industry events with filters by time range and industry. Each past event gets an AI-generated summary analyzing what happened and why it matters to Nyriom.

## Tech Stack

- **Backend:** Python / Flask
- **Database:** Supabase (PostgreSQL)
- **AI:** Perplexity API (sonar + sonar-pro)
- **Frontend:** Jinja2 + Tailwind CSS (CDN with typography plugin)
- **Deployment:** Vercel (serverless)
- **PWA:** Installable on iOS + Android with offline support
- **Security:** nh3 HTML sanitization, CSRF protection (flask-wtf), Content Security Policy

## Architecture

```
nyriom-intel-hub/
├── main.py                              # Flask app — routes, auth, security middleware
├── services/
│   └── perplexity_service.py            # Two-pass AI pipeline (sonar → sonar-pro)
├── templates/
│   ├── base.html                        # Layout, nav, shared JS (NyriomDropdown utility)
│   ├── home.html                        # Landing page
│   ├── index.html                       # Dashboard — vertical selector + editorial layout
│   ├── events.html                      # Event listing with industry/time filters
│   ├── event_detail.html                # Single event + AI summary
│   ├── archive.html                     # Historical report archive
│   ├── report_view.html                 # Printable intelligence report
│   ├── login.html                       # Demo/guest auth
│   ├── admin.html                       # Admin panel
│   ├── upload_events.html               # CSV bulk upload
│   └── offline.html                     # PWA offline fallback
├── static/
│   ├── icons/                           # PWA icons (192px, 512px)
│   ├── manifest.json                    # PWA manifest
│   └── service-worker.js               # Caching + offline strategy
├── scripts/
│   ├── seed_data.py                     # Wipe + seed events from CSV
│   ├── generate_summaries.py            # Generate AI event summaries
│   ├── generate_intelligence_reports.py # Generate weekly vertical reports
│   ├── delete_and_regenerate_reports.py # Wipe intelligence reports
│   └── add_events.py                    # Add events without wiping
├── data/
│   └── sample_events.csv               # 36 events across 4 verticals
├── .github/workflows/
│   └── weekly-intelligence.yml          # Monday 8am UTC cron for report generation
├── docs/screenshots/                    # App screenshots
└── vercel.json                          # Vercel deployment config
```

## Local Development

```bash
git clone https://github.com/lorenzo-leprotti/nyriom-intelligence.git
cd nyriom-intel-hub
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase + Perplexity API keys

# Run (port 5001 — port 5000 is blocked by macOS AirPlay)
python -c "from dotenv import load_dotenv; load_dotenv(); from main import app; app.run(host='0.0.0.0', port=5001)"
```

Then open `http://localhost:5001`

**Demo credentials:** password `demo2026` — or enter as guest (no credentials).

## Environment Variables

See `.env.example` for the full list. Required:

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `FLASK_SECRET_KEY` | Session encryption |
| `PERPLEXITY_API_KEY` | AI summary/report generation |
| `ADMIN_SECRET` | Admin panel password |
| `DEMO_PASSWORD` | Demo login password |

## Supabase Tables

| Table | Purpose |
|-------|---------|
| `events` | Industry events (name, industry, dates, location, website, description) |
| `event_summaries` | AI-generated post-event analysis |
| `intelligence_reports` | Weekly reports per vertical (report_html + top_3_json) |
| `app_config` | Key-value store (app_version for PWA cache busting) |

## Related Projects

| Project | Description |
|---------|-------------|
| [Nyriom List](https://github.com/lorenzo-leprotti/nyriom-list) | AI-powered conference delegate prioritization pipeline |
| [Nyriom Dashboard](https://github.com/lorenzo-leprotti/nyriom-dashboard) | Sustainability impact simulator (React/TypeScript) |

## Disclosure

This is a portfolio demonstration project. **Nyriom Technologies** is a fictional advanced materials startup. Industry events and companies referenced are real; the company context is generated. The pipeline architecture, AI prompts, and code are production-representative.

## License

MIT

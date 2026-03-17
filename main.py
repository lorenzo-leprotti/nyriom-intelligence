import os
import json
import ast
import secrets
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, make_response
from flask_wtf.csrf import CSRFProtect
from datetime import date, datetime
import csv
import io
from supabase import create_client, Client
from services.perplexity_service import generate_event_summary, sanitize_html
from urllib.parse import urlparse


def is_safe_redirect_url(url):
    """Validate that a redirect URL is safe (internal path only)."""
    if not url:
        return False
    parsed = urlparse(url)
    return (not parsed.scheme and not parsed.netloc and url.startswith('/'))


app = Flask(__name__)

# Secret key for session encryption
_secret_key = os.environ.get('FLASK_SECRET_KEY')
if not _secret_key:
    if os.environ.get('VERCEL'):
        raise RuntimeError("FLASK_SECRET_KEY environment variable must be set in production!")
    else:
        _secret_key = secrets.token_hex(32)
        print("[WARNING] FLASK_SECRET_KEY not set - using random key for local development")
app.secret_key = _secret_key

# Session cookie configuration
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# CSRF protection
csrf = CSRFProtect(app)


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if os.environ.get('VERCEL'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# Demo password for portfolio demo access
if os.environ.get('VERCEL'):
    DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD')
    if not DEMO_PASSWORD:
        print("[WARNING] DEMO_PASSWORD not set in production!")
else:
    DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', 'demo2026')


@app.context_processor
def inject_user():
    """Make user info available in all templates."""
    is_admin = session.get('admin_authenticated', False)

    user = session.get('user', None)
    user_type = None
    if user:
        if user.get('is_guest'):
            user_type = 'guest'
        elif user.get('user_type') == 'demo':
            user_type = 'demo'

    return {
        'current_user': user,
        'user_type': user_type,
        'is_admin': is_admin,
    }


def is_user_authenticated():
    """Check if current user is authenticated."""
    return 'user' in session


def get_current_user():
    """Get current user info from session."""
    return session.get('user', None)


# --- SUPABASE CLIENT ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError(f"Missing Supabase credentials! URL: {bool(url)}, KEY: {bool(key)}")

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    raise ValueError(f"Failed to create Supabase client. Error: {e}")


# --- APP CONFIG HELPER FUNCTIONS ---
def get_app_config(key):
    """Fetches a config value from app_config table."""
    try:
        response = supabase.table('app_config') \
            .select('value') \
            .eq('key', key) \
            .limit(1) \
            .execute()
        return response.data[0]['value'] if response.data else None
    except Exception as e:
        print(f"Error fetching app config {key}: {e}")
        return None


def update_app_config(key, value):
    """Updates a config value in app_config table."""
    try:
        response = supabase.table('app_config') \
            .update({'value': value}) \
            .eq('key', key) \
            .execute()
        return True
    except Exception as e:
        print(f"Error updating app config {key}: {e}")
        return False


# --- AUTHENTICATION MIDDLEWARE ---
@app.before_request
def check_auth():
    """Check authentication before every request."""
    public_paths = [
        '/login',
        '/auth/',
        '/guest',
        '/logout',
        '/static/',
        '/api/version',
        '/manifest.json',
        '/service-worker.js',
        '/offline',
    ]

    for path in public_paths:
        if request.path.startswith(path):
            return None

    # Admin paths have their own auth
    if request.path.startswith('/admin'):
        return None

    # Require login
    if not is_user_authenticated():
        if not request.path.startswith('/favicon') and '.' not in request.path:
            session['next_url'] = request.path
        return redirect(url_for('login'))

    return None


# --- AUTHENTICATION ROUTES ---
@app.route('/login')
def login():
    """Show login page."""
    if is_user_authenticated():
        return redirect(url_for('home'))

    error = request.args.get('error')
    logged_out = request.args.get('logged_out') == 'true'
    return render_template('login.html', error=error, logged_out=logged_out)


@app.route('/auth/demo', methods=['POST'])
def auth_demo():
    """Demo login with shared password."""
    password = request.form.get('password', '')
    if password == DEMO_PASSWORD:
        session['user'] = {
            'name': 'Demo User',
            'email': 'demo@nyriom.tech',
            'user_type': 'demo'
        }
        session.permanent = True
        next_url = session.pop('next_url', None)
        if not next_url or not is_safe_redirect_url(next_url):
            next_url = '/'
        return redirect(next_url)
    return redirect(url_for('login', error='Invalid password'))


@app.route('/guest')
def guest_login():
    """Allow guest access."""
    session['user'] = {
        'name': 'Guest',
        'email': 'guest@nyriom.tech',
        'is_guest': True
    }
    session.permanent = True

    next_url = request.args.get('next') or session.pop('next_url', None)
    if not next_url or next_url == '/login' or not is_safe_redirect_url(next_url):
        next_url = '/'
    return redirect(next_url)


@app.route('/logout')
def logout():
    """Log out the user."""
    session.clear()
    return redirect(url_for('login', logged_out='true'))


# --- HELPER FUNCTION: Fetch & Clean Data ---
def get_latest_report(vertical_name):
    """Fetches and cleans the latest report for a given vertical."""
    try:
        response = supabase.table('intelligence_reports') \
            .select("*") \
            .eq('vertical', vertical_name) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()

        data = response.data[0] if response.data else None

        if data and isinstance(data, dict):
            top_3 = data.get('top_3_json')
            if isinstance(top_3, str):
                top_3 = top_3.replace('```json', '').replace('```', '').strip()
                try:
                    data['top_3_json'] = json.loads(top_3)
                except json.JSONDecodeError:
                    try:
                        data['top_3_json'] = ast.literal_eval(top_3)
                    except Exception as e:
                        print(f"Failed to parse JSON for {vertical_name}: {e}")
                        data['top_3_json'] = []

            report_html = data.get('report_html')
            if isinstance(report_html, str):
                report_html = report_html.replace('\\n', '\n').strip('"')
                data['report_html'] = sanitize_html(report_html)

        return data
    except Exception as e:
        print(f"Error fetching {vertical_name}: {e}")
        return None


# --- EVENTS HELPER FUNCTIONS ---
def get_all_events(filter_type='upcoming', industry=None):
    """Fetches events with optional filtering."""
    try:
        from datetime import timedelta

        query = supabase.table('events').select("*")

        if industry and industry != 'all':
            query = query.eq('industry', industry)

        today = date.today()

        if filter_type == '3months':
            three_months_out = (today + timedelta(days=90)).isoformat()
            query = query.gte('start_date', today.isoformat()).lte('start_date', three_months_out)
        elif filter_type == 'upcoming':
            query = query.gte('start_date', today.isoformat())
        elif filter_type == 'past':
            query = query.lt('start_date', today.isoformat())

        order_desc = (filter_type == 'past')
        response = query.order('start_date', desc=order_desc).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching events: {e}")
        return []


def get_event_by_id(event_id):
    """Fetches a single event by ID."""
    try:
        response = supabase.table('events') \
            .select("*") \
            .eq('id', event_id) \
            .limit(1) \
            .execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error fetching event {event_id}: {e}")
        return None


# --- ROUTES ---

@app.route('/')
def home():
    """The Landing Page."""
    return render_template('home.html')


@app.route('/dashboard')
def dashboard():
    """The Main Dashboard — fetches reports for all 4 verticals."""
    aerospace = get_latest_report('aerospace')
    automotive = get_latest_report('automotive')
    robotics = get_latest_report('robotics')
    ai_electronics = get_latest_report('ai_electronics')

    query_industry = request.args.get('industry')
    if query_industry and query_industry in ['Aerospace', 'Automotive', 'Robotics', 'AI/Electronics']:
        default_industry = query_industry
    else:
        default_industry = 'Aerospace'

    return render_template('index.html',
                           aerospace_data=aerospace,
                           automotive_data=automotive,
                           robotics_data=robotics,
                           ai_electronics_data=ai_electronics,
                           default_industry=default_industry)


@app.route('/archive')
def archive():
    """Archive page with search/filter capability."""
    try:
        from datetime import timedelta

        vertical = request.args.get('vertical', 'all')
        timeframe = request.args.get('timeframe', '3months')

        query = supabase.table('intelligence_reports').select("*")

        if vertical and vertical != 'all':
            query = query.eq('vertical', vertical.lower())

        today = date.today()
        if timeframe == '1month':
            cutoff = (today - timedelta(days=30)).isoformat()
            query = query.gte('created_at', cutoff)
        elif timeframe == '3months':
            cutoff = (today - timedelta(days=90)).isoformat()
            query = query.gte('created_at', cutoff)

        response = query.order('created_at', desc=True).limit(8).execute()

        return render_template('archive.html',
                             reports=response.data,
                             current_vertical=vertical,
                             current_timeframe=timeframe)
    except Exception as e:
        print(f"Archive error: {e}")
        return "<h1>Something went wrong</h1><p>Please try again later.</p>", 500


@app.route('/report/<report_id>')
def view_report(report_id):
    """View a single intelligence report in a clean, printable layout."""
    try:
        response = supabase.table('intelligence_reports') \
            .select("*") \
            .eq('id', report_id) \
            .execute()

        if not response.data:
            return "Report not found", 404

        report = response.data[0]
        report_html = report.get('report_html', '')
        if isinstance(report_html, str):
            report_html = report_html.replace('\\n', '\n').strip('"')
            report_html = sanitize_html(report_html)

        vertical = report.get('vertical', '')
        vertical_display = vertical.replace('_', '/').title()
        vertical_class_map = {
            'Aerospace': 'aerospace',
            'Automotive': 'automotive',
            'Robotics': 'robotics',
            'AI_Electronics': 'ai-electronics',
            'AI/Electronics': 'ai-electronics',
        }
        vertical_class = vertical_class_map.get(vertical, 'aerospace')

        return render_template('report_view.html',
                             report=report,
                             report_html=report_html,
                             vertical_display=vertical_display,
                             vertical_class=vertical_class)
    except Exception as e:
        print(f"Report error: {e}")
        return "<h1>Something went wrong</h1><p>Please try again later.</p>", 500


# --- EVENTS ROUTES ---

@app.route('/events')
def events():
    """Events listing page with filters and pagination."""
    filter_type = request.args.get('filter', 'upcoming')

    industry = request.args.get('industry', 'all')
    if industry == '':
        industry = 'all'

    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 8
    offset = (page - 1) * per_page

    all_events = get_all_events(filter_type, industry)
    today = date.today()

    upcoming_events = []
    for event in all_events:
        if not event:
            continue
        try:
            start_date = datetime.strptime(event['start_date'], '%Y-%m-%d').date()
            end_date_str = event.get('end_date') or event['start_date']
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            days_until = (start_date - today).days
            event['days_until'] = days_until
            event['is_upcoming'] = 0 < days_until <= 14
            event['is_past'] = end_date < today
            event['is_this_week'] = 0 < days_until <= 7

            if 0 < days_until <= 14:
                upcoming_events.append(event)
        except Exception:
            event['days_until'] = None
            event['is_upcoming'] = False
            event['is_past'] = False
            event['is_this_week'] = False

    upcoming_events.sort(key=lambda x: x.get('days_until', 999))

    total_events = len(all_events)
    total_pages = (total_events + per_page - 1) // per_page
    events_list = all_events[offset:offset + per_page]

    return render_template('events.html',
                           events=events_list,
                           upcoming_events=upcoming_events,
                           current_filter=filter_type,
                           current_industry=industry,
                           current_page=page,
                           total_pages=total_pages,
                           has_next=page < total_pages,
                           has_prev=page > 1)


@app.route('/events/<event_id>')
def event_detail(event_id):
    """Single event detail page with AI summary."""
    event = get_event_by_id(event_id)
    if not event:
        return "<h3>Event not found</h3>", 404

    summary = None
    try:
        summary_response = supabase.table('event_summaries') \
            .select('*') \
            .eq('event_id', event_id) \
            .eq('status', 'completed') \
            .limit(1) \
            .execute()
        summary = summary_response.data[0] if summary_response.data else None
    except Exception as e:
        print(f"Error fetching summary: {e}")

    end_date_str = event.get('end_date') or event.get('start_date')
    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        is_past_event = end_date < date.today()
    except Exception:
        is_past_event = False

    return render_template('event_detail.html',
                           event=event,
                           summary=summary,
                           is_past_event=is_past_event)


@app.route('/upload-events', methods=['GET', 'POST'])
def upload_events():
    """CSV upload for events - Admin only."""
    if not session.get('admin_authenticated'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('upload_events.html', error="No file selected")

        file = request.files['file']
        if not file.filename or file.filename == '':
            return render_template('upload_events.html', error="No file selected")

        if not file.filename.endswith('.csv'):
            return render_template('upload_events.html', error="Please upload a CSV file")

        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)

            count = 0
            skipped = 0
            for row in reader:
                event_data = {
                    'name': row.get('name', '').strip(),
                    'industry': row.get('industry', '').strip() or None,
                    'start_date': row.get('start_date', '').strip(),
                    'end_date': row.get('end_date', '').strip() or None,
                    'location': row.get('location', '').strip() or None,
                    'country': row.get('country', '').strip() or None,
                    'website': row.get('website', '').strip() or None,
                    'description': row.get('description', '').strip() or None,
                }

                if event_data['name'] and event_data['start_date']:
                    existing = supabase.table('events') \
                        .select('id') \
                        .eq('name', event_data['name']) \
                        .eq('start_date', event_data['start_date']) \
                        .execute()

                    if existing.data:
                        skipped += 1
                        continue

                    supabase.table('events').insert(event_data).execute()
                    count += 1

            return redirect(url_for('events') + f'?uploaded={count}&skipped={skipped}')

        except Exception as e:
            print(f"CSV upload error: {e}")
            return render_template('upload_events.html', error="Error processing file. Please check the format and try again.")

    return render_template('upload_events.html')


@app.route('/offline')
def offline():
    """Offline fallback page for PWA."""
    return render_template('offline.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin panel with summary generation controls."""
    if os.environ.get('VERCEL'):
        admin_secret = os.environ.get('ADMIN_SECRET')
        if not admin_secret:
            print("[WARNING] ADMIN_SECRET not set in production!")
            return render_template('admin.html', authenticated=False, login_error="Admin access is not configured.")
    else:
        admin_secret = os.environ.get('ADMIN_SECRET', 'admin2026')

    is_authenticated = session.get('admin_authenticated')

    # Rate limiting (5 attempts -> 15 min cooldown)
    MAX_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    failed_attempts = session.get('admin_failed_attempts', 0)
    lockout_until = session.get('admin_lockout_until')

    if lockout_until:
        lockout_time = datetime.fromisoformat(lockout_until)
        if datetime.now() < lockout_time:
            remaining = int((lockout_time - datetime.now()).total_seconds() / 60) + 1
            return render_template('admin.html',
                                   authenticated=False,
                                   login_error=f"Too many failed attempts. Try again in {remaining} minutes.")
        else:
            session.pop('admin_lockout_until', None)
            session.pop('admin_failed_attempts', None)
            failed_attempts = 0

    if request.method == 'POST' and request.form.get('action') == 'login':
        password = request.form.get('password', '')
        if password == admin_secret:
            session.pop('admin_failed_attempts', None)
            session.pop('admin_lockout_until', None)
            session['admin_authenticated'] = True
            session.permanent = True
            return redirect(url_for('admin'))
        else:
            failed_attempts += 1
            session['admin_failed_attempts'] = failed_attempts
            if failed_attempts >= MAX_ATTEMPTS:
                from datetime import timedelta
                lockout_time = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
                session['admin_lockout_until'] = lockout_time.isoformat()
                return render_template('admin.html',
                                       authenticated=False,
                                       login_error=f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.")
            remaining_attempts = MAX_ATTEMPTS - failed_attempts
            return render_template('admin.html',
                                   authenticated=False,
                                   login_error=f"Invalid password. {remaining_attempts} attempts remaining.")

    if not is_authenticated:
        return render_template('admin.html', authenticated=False)

    # Authenticated: fetch events without summaries for admin panel
    events_without_summaries = []
    try:
        all_events_resp = supabase.table('events').select('id, name, start_date, end_date, industry').execute()
        summaries_resp = supabase.table('event_summaries').select('event_id').eq('status', 'completed').execute()
        completed_ids = {s['event_id'] for s in summaries_resp.data} if summaries_resp.data else set()

        today = date.today()
        for ev in (all_events_resp.data or []):
            end_str = ev.get('end_date') or ev.get('start_date', '')
            try:
                end_dt = datetime.strptime(end_str, '%Y-%m-%d').date()
                if end_dt < today and ev['id'] not in completed_ids:
                    events_without_summaries.append(ev)
            except Exception:
                pass
    except Exception as e:
        print(f"Error fetching events for admin: {e}")

    return render_template('admin.html',
                           authenticated=True,
                           events_without_summaries=events_without_summaries)


@app.route('/admin/logout')
def admin_logout():
    """Logout from admin panel."""
    session.pop('admin_authenticated', None)
    return redirect(url_for('home'))


# --- API ENDPOINTS ---

@csrf.exempt
@app.route('/api/version')
def api_version():
    """Returns app version info for service worker update checks."""
    version_config = get_app_config('app_version')
    if version_config:
        return jsonify({
            'version': version_config.get('version', '1.0.0'),
            'min_version': version_config.get('min_version', '1.0.0')
        })
    return jsonify({'version': '1.0.0', 'min_version': '1.0.0'})


@app.route('/api/generate-summary', methods=['POST'])
def api_generate_summary():
    """Admin-triggered summary generation for a single event."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized — admin login required'}), 401

    data = request.get_json()
    event_id = data.get('event_id') if data else None
    if not event_id:
        return jsonify({'error': 'event_id required'}), 400

    # Fetch event
    try:
        event_response = supabase.table('events').select('*').eq('id', event_id).single().execute()
        event = event_response.data
    except Exception as e:
        print(f"Event lookup error: {e}")
        return jsonify({'error': 'Event not found'}), 404

    if not event:
        return jsonify({'error': 'Event not found'}), 404

    # Generate summary via Perplexity
    result = generate_event_summary(
        event_name=event['name'],
        event_date=event.get('end_date') or event['start_date'],
        industry=event.get('industry', 'General'),
        location=event.get('location', 'Unknown'),
        website=event.get('website')
    )

    if result['success']:
        try:
            supabase.table('event_summaries').upsert({
                'event_id': event_id,
                'summary_text': result['summary'],
                'status': 'completed'
            }, on_conflict='event_id').execute()
            return jsonify({'success': True, 'event_name': event['name']})
        except Exception as e:
            print(f"Failed to save summary: {e}")
            return jsonify({'error': 'Failed to save summary'}), 500
    else:
        try:
            supabase.table('event_summaries').upsert({
                'event_id': event_id,
                'summary_text': '',
                'status': 'failed'
            }, on_conflict='event_id').execute()
        except Exception:
            pass
        return jsonify({'success': False, 'error': result['error']}), 500


@app.route('/api/events-without-summaries')
def api_events_without_summaries():
    """Returns past events that don't have completed summaries."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        all_events_resp = supabase.table('events').select('id, name, start_date, end_date, industry').execute()
        summaries_resp = supabase.table('event_summaries').select('event_id').eq('status', 'completed').execute()
        completed_ids = {s['event_id'] for s in summaries_resp.data} if summaries_resp.data else set()

        today = date.today()
        missing = []
        for ev in (all_events_resp.data or []):
            end_str = ev.get('end_date') or ev.get('start_date', '')
            try:
                end_dt = datetime.strptime(end_str, '%Y-%m-%d').date()
                if end_dt < today and ev['id'] not in completed_ids:
                    missing.append(ev)
            except Exception:
                pass

        return jsonify({'events': missing, 'count': len(missing)})
    except Exception as e:
        print(f"Events-without-summaries error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/manifest.json')
def manifest():
    """Serve PWA manifest file."""
    from flask import send_from_directory
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')


@app.route('/service-worker.js')
def service_worker():
    """Serve service worker file."""
    from flask import send_from_directory
    return send_from_directory('static', 'service-worker.js', mimetype='application/javascript')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

# Census Project Workplan Tracking Application

A web application for **Statistics Sierra Leone** to track Census workplan implementation in one place: upload the existing Excel workbook (or a single worksheet), monitor progress on a live dashboard, hold responsible officers accountable, and get automatic email alerts before deadlines slip.

Built with Django. Designed to outgrow the current workbook: projects and workstreams are ordinary database records, not hard-coded, so a future census (or any other workplan) can be tracked the same way without a code change.

## Features

- **Dashboard** — total activities/milestones, completion by status and workstream, activities due today/this week/7/14/30 days, overdue activities, activities with no assigned owner, a project Gantt timeline, and an overall readiness indicator.
- **Filterable activity list** — by workstream, responsible person, status, start/end date, and phase.
- **Detailed activity records** — dates, dependency, expected deliverable, owner, status, progress %, comments, and a full change history (who changed what, when, and whether it came from a manual edit or a workbook upload).
- **Workbook upload** — upload the full Census workbook or a single worksheet (`.xlsx` or `.csv`). Column names are matched automatically (with a fuzzy-matching fallback) against the expected fields, previewed and validated before anything is saved, and re-uploading updates existing activities instead of duplicating them — with every change logged.
- **Email notifications** — task assignment, approaching/overdue deadlines, "at risk" flags, status changes, milestone completions, and workstream-level overdue alerts, plus a weekly summary digest to each project owner. Reminder windows and thresholds are configurable from the app.
- **Roles** — Administrator, Project Owner, Workstream Owner, Contributor, Viewer, each with different edit/manage permissions.

## Tech stack

| Layer | Choice |
|---|---|
| Backend / templates | Django 5.2 (LTS) |
| Database | SQLite by default; PostgreSQL via `DATABASE_URL` |
| Workbook parsing | pandas, openpyxl, rapidfuzz (fuzzy column matching) |
| Frontend | Django templates, Bootstrap 5, Chart.js, Frappe Gantt (all via CDN — no Node build step) |
| Email | Django's email backend (console in dev, SMTP in production) |
| Scheduling | APScheduler, running in-process for daily deadline checks + the weekly digest |
| Static files | WhiteNoise |

## Project structure

```
census_tracker/        Django project settings, root URLconf
apps/
  accounts/             Custom User model, roles, login, user management
  projects/             Project and Workstream models
  activities/            Activity, ActivityHistory, Comment models + views
  uploads/               Workbook parsing, column mapping, preview/commit, upload history
  dashboard/             KPI aggregation, filters, chart/Gantt JSON endpoints
  notifications/         Notification rules/log, email templates, signal handlers, scheduled jobs
templates/               HTML templates, organised per app, plus templates/emails/
static/                  Custom CSS/JS
sample_data/             Sample workbook + demo data seed command
```

## Getting started (local development)

Requires Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

copy .env.example .env        # Windows: copy; macOS/Linux: cp
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://localhost:8000`. To explore the app with realistic sample data instead of starting from empty:

```bash
python manage.py seed_demo_data
```

This creates one user per role (`admin`, `pmoore`, `wskamara`, `ckoroma`, `vsesay`, all with password `admin12345`), a sample census project with the nine workstreams from the original workbook, and ~90 sample activities across a range of statuses and dates.

A sample workbook for testing the upload flow is at `sample_data/sample_census_workplan.xlsx`.

### Running the notification scheduler

With `SCHEDULER_ENABLED=True` (the default), the app starts an in-process scheduler on boot that runs `check_deadlines` daily at 07:00 and `send_weekly_digest` every Monday at 07:30. This is enough for a single-process deployment. If you run more than one app server process/worker, disable it (`SCHEDULER_ENABLED=False`) and schedule these instead via cron / Windows Task Scheduler so the jobs don't run once per process:

```bash
python manage.py check_deadlines
python manage.py send_weekly_digest
```

## Environment variables

Copy `.env.example` to `.env` and fill in real values. Full reference:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *(insecure placeholder)* | Django secret key — set a real random value in production |
| `DEBUG` | `False` | Django debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hostnames |
| `CSRF_TRUSTED_ORIGINS` | *(empty)* | Comma-separated origins, needed if served behind a reverse proxy on HTTPS |
| `TIME_ZONE` | `Africa/Freetown` | Django time zone |
| `DATABASE_URL` | SQLite file | e.g. `postgres://user:password@host:5432/dbname` |
| `EMAIL_BACKEND` | console (dev) / smtp (prod) | Django email backend |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | — | SMTP credentials |
| `DEFAULT_FROM_EMAIL` | — | From address for outgoing notification emails |
| `SITE_NAME`, `SITE_URL` | — | Used in email templates and links |
| `SCHEDULER_ENABLED` | `True` | Whether the app runs the in-process notification scheduler |
| `REMINDER_DAYS` | `1,3,7,14` | Default deadline-reminder windows, seeded once on first migrate (editable afterwards from Notification Settings) |
| `WORKSTREAM_OVERDUE_THRESHOLD` | `3` | Default overdue-activity count that triggers a workstream alert |

**Never commit `.env`** — it's already excluded via `.gitignore`.

## Running tests

```bash
python manage.py test
```

## Deployment

### Docker

```bash
cp .env.example .env   # edit with real production values
docker compose up -d --build
```

This starts the app (via Gunicorn) and a PostgreSQL database, running migrations automatically on startup. Set real `POSTGRES_*` values in `.env` before deploying.

### Manual

1. Set `DEBUG=False` and a real `SECRET_KEY` in your environment.
2. Point `DATABASE_URL` at a PostgreSQL instance.
3. `pip install -r requirements.txt`
4. `python manage.py migrate`
5. `python manage.py collectstatic --noinput`
6. Run behind Gunicorn (`gunicorn census_tracker.wsgi:application`) and a reverse proxy (nginx, etc.) that terminates TLS.

## Uploading a workplan

1. Go to **Upload Workplan**, choose the project, and optionally a single workstream (leave blank to upload the full workbook — each worksheet is matched to, or creates, its own workstream).
2. Choose an `.xlsx` or `.csv` file.
3. On the review screen, check the auto-detected column mapping for each worksheet and correct anything mismatched, then check the validation summary (rows that will be skipped, and why).
4. Confirm to import. Existing activities (matched by workstream + activity name) are updated in place, with every changed field recorded in that activity's change history; everything else is created new.

## Roles

| Role | Can do |
|---|---|
| Administrator | Everything: manage users, projects, notification settings, all activities |
| Project Owner | Manage their project's workstreams and activities; receives the weekly digest |
| Workstream Owner | Edit activities within their assigned workstream(s) |
| Contributor | Update status/progress/comments on activities they're responsible for |
| Viewer | Read-only access everywhere |

## Roadmap

- Multiple concurrent census projects side-by-side (the data model already supports it — this is UI work)
- Bulk activity actions (reassign, bulk status update)
- Export dashboard/report to PDF or Excel

## License

MIT — see [LICENSE](LICENSE). Statistics Sierra Leone should confirm this is the intended license for the deployed instance before publishing publicly.

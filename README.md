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
- **Branding & countdown** — the official census logo appears in the navbar and login page (`static/img/census_logo.jpeg`), and a live countdown to a project's Census Day is shown in the navbar and as a banner on the dashboard once that project's `census_day` is set (Projects → Edit project).

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

### Render (public hosting, free tier)

This is the quickest way to get the app reachable on the public internet with a free URL. `render.yaml` in the repo root defines everything Render needs to build it (see [Render's Blueprint docs](https://render.com/docs/infrastructure-as-code) for the current field reference, in case Render's schema has moved on since this was written).

1. **Push this repo to GitHub** if it isn't already (Render deploys from a Git repo, not a local folder).
2. **Create a free Render account** at [render.com](https://render.com) — this step has to be done by a person, not an assistant: hosting accounts and payment methods aren't something that should be created on your behalf.
3. In the Render dashboard, **New +** → **Blueprint**, and point it at this GitHub repo. Render reads `render.yaml` and proposes three resources: the `census-workplan-tracker` web service, a free PostgreSQL database, and two Cron Jobs (`census-check-deadlines`, `census-weekly-digest`).
4. Render will prompt for the environment variables marked `sync: false` in `render.yaml` before the first deploy — fill these in for the web service (the two Cron Jobs need the same `SECRET_KEY` and email settings, kept in sync manually since Render doesn't share values between services automatically):

   | Variable | Value |
   |---|---|
   | `EMAIL_HOST` | your SMTP host, e.g. `mail.statistics.sl` |
   | `EMAIL_PORT` | `465` for implicit SSL, `587` for STARTTLS |
   | `EMAIL_USE_SSL` / `EMAIL_USE_TLS` | `True` for exactly one of these, matching the port above |
   | `EMAIL_HOST_USER` | the sending mailbox, e.g. `project@statistics.sl` |
   | `EMAIL_HOST_PASSWORD` | that mailbox's password |
   | `DEFAULT_FROM_EMAIL` | e.g. `Census Workplan Tracker <project@statistics.sl>` |
   | `SITE_URL` | the `https://...onrender.com` URL Render assigns (fill in *after* the first deploy, then redeploy) |

5. Deploy. Render builds the Docker image, runs migrations automatically (baked into the image's start command), and the app comes up at `https://<service-name>.onrender.com`.
6. Log in with the admin account you created locally (`python manage.py createsuperuser`) — or, since the free Postgres starts empty, create one against the live database via Render's shell tab: **Dashboard → web service → Shell** → `python manage.py createsuperuser`.

**Free-tier things worth knowing before you rely on this in production:**
- The free web service **sleeps after ~15 minutes of no traffic** and takes a few seconds to wake back up on the next request — fine for a small team, noticeable for a first-thing-in-the-morning check. This is *why* the scheduled emails run as separate Cron Jobs rather than the in-process scheduler: cron jobs run on their own regardless of whether the web service is asleep.
- Render's **free PostgreSQL database has a retention limit** (historically ~30 days before it's deleted, though check current terms at signup — this changes over time) — fine for a trial, but budget for Render's paid database tier before this becomes the system of record.
- The workbook upload wizard's preview step writes a temporary file to local disk between "upload" and "confirm" — on the free plan the container's filesystem isn't a persistent disk, so this works in normal single-instance operation but isn't bulletproof against a container restart landing exactly between those two requests. Not a concern for the deadline/status features, just something to know if an upload confirmation ever fails with a missing-file error — retry the upload.
- Upgrading to Render's paid Starter plan (~$7/mo at time of writing) removes the sleep behavior and is a reasonable next step once this is genuinely in daily use.

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
| Project Owner | Manage their project's workstreams and activities; receives the weekly digest and completion-validated alerts |
| Workstream Owner | Edit activities within their assigned workstream(s); validates (or sends back) activities a Contributor has marked Pending Validation |
| Contributor | Update status/progress/comments on activities they're responsible for; can mark work Pending Validation but not Completed directly |
| Viewer | Read-only access everywhere |

Each Workstream also has an optional **Backup Lead** (Projects → a workstream → Edit workstream), who has the same edit/validate rights as the Lead and is included on workstream-level alerts -- useful for covering absences. When an activity's Responsible field isn't a matched system account (e.g. it only carries a role title like "GIS LEAD" from an uploaded workbook), owner-level notifications (status changes, at-risk, validation requests) fall back to that workstream's Lead + Backup Lead so alerts still reach someone accountable.

### Completion validation workflow

1. A Contributor sets an activity's status to **Pending Validation** once they believe the work is done (they cannot set it to Completed directly).
2. The workstream's Lead and Backup Lead are emailed a validation request.
3. From the activity page, the Lead/Backup Lead (or Admin/Project Owner) either **Validate & Complete** it (records who validated it and when, and emails the Project Owner) or **Send it back** to Ongoing with an optional comment explaining why.

## Roadmap

- Multiple concurrent census projects side-by-side (the data model already supports it — this is UI work)
- Bulk activity actions (reassign, bulk status update)
- Export dashboard/report to PDF or Excel

## License

MIT — see [LICENSE](LICENSE). Statistics Sierra Leone should confirm this is the intended license for the deployed instance before publishing publicly.

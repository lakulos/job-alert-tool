# Job Alert

A one-shot, rule-based Python tool that finds fresh **Cloud Engineer / Architect**, **DevOps Engineer**, and **Site Reliability Engineer (SRE)** jobs. It keeps only vacancies that explicitly offer **visa sponsorship or relocation**, or are explicitly **fully remote from anywhere in the world**, then sends one Gmail digest. You review and apply manually.

There are **no LLM/AI calls at runtime**, no Telegram integration, and no application automation.

## Sources

- Greenhouse, Lever, and Ashby public board APIs
- [Remote OK API](https://remoteok.com/api), with required source attribution
- [Jobicy API](https://jobicy.com/jobs-rss-feed), with required source attribution
- [Himalayas Jobs API](https://himalayas.app/jobs/api), fetched incrementally with attribution
- [Remotive API](https://remotive.com/api-documentation) (digest links back and identifies Remotive)
- We Work Remotely DevOps/Sysadmin RSS
- SmartRecruiters public Posting API for configured company identifiers
- Recruitee Careers Site API for configured tenant slugs
- [Arbeitnow API](https://www.arbeitnow.com/blog/job-board-api), using `visa_sponsorship=true`
- Jooble API, queried once per role and track
- MyJobMag's working detailed RSS feed (`jobsxml_by_categories.xml`)
- Allowlisted LinkedIn, Wellfound, Jobberman, MyJobMag, and Hot Nigerian Jobs alert emails through read-only Gmail IMAP
- Optional per-board Apify actors, disabled by default
- Weekly cached [UK licensed sponsor register](https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers)

The starter ATS slugs in `config.yaml` were live-checked on 2026-10-16. Greenhouse (`boards.greenhouse.io`), Lever (`job.lever.co`), SmartRecruiters, and Recruitee use public company/tenant APIs, but do not provide global company discovery. Add identifiers under `sources.greenhouse.slugs`, `sources.lever.slugs`, `sources.smartrecruiters.companies`, and `sources.recruitee.tenants`. Public boards change; remove a company when its board no longer works.

A Recruitee tenant may be a plain slug or `{slug: company, token_env: RECRUITEE_COMPANY_TOKEN}`. Tokens are read from environment variables, never YAML. Recruitee has announced that Careers Site API tokens become mandatory on February 10, 2027; obtain the token from each employer you monitor or disable that tenant. The app will not fall back to scraping.

Remote OK, Jobicy, and Himalayas results preserve provider attribution and supplied application/source links. Himalayas is read only until postings cross the 48-hour freshness boundary; the app never traverses its full job corpus.

LinkedIn has no suitable public jobs API for this tool. It is covered through job-alert emails you elect to receive, not direct scraping, login automation, or bot-protection bypasses. Optional user-configured Apify actors remain available for sites whose current terms permit them.

### Jooble

Jooble requires a separate API key. The app queries each supported role for worldwide-remote and visa/relocation terms, handles empty/error responses without stopping other sources, and then applies the same strict evidence rules as every other source. A search-query match alone never makes a job eligible.

## Docker image

The public image is available as:

```text
lakulos/job-alert-tool:latest
```

Versioned releases are also published, for example `lakulos/job-alert-tool:0.1.0`. Source and the Dockerfile are available at [github.com/lakulos/job-alert-tool](https://github.com/lakulos/job-alert-tool).

To build the current source locally instead:

```bash
docker build -t job-alert-tool:local .
```

## Windows Docker Desktop (recommended)

The published image runs continuously and schedules checks at **07:07 and 19:07 Africa/Lagos time**. It also runs once when the container first starts. Docker Desktop must be running, and the Windows computer must be awake and online when a check is due.

Create a folder such as `C:\job-alert` containing:

- `compose.yaml`
- `config.yaml`
- `.env` copied from `.env.example` and filled locally

The image already contains the application. In PowerShell, from that folder:

```powershell
docker compose pull
docker compose up -d
docker compose logs -f scheduler
```

Runtime credentials are read from `.env` on the Windows host; they are not embedded in the image. `config.yaml` is mounted read-only. Delivery history and the UK sponsor cache live in a named Docker volume so updates and container replacement do not cause duplicate alerts.

Useful commands:

```powershell
# Check status and recent logs
docker compose ps
docker compose logs --tail 100 scheduler

# Trigger one live run now (may send a digest)
docker compose run --rm --entrypoint /usr/bin/tini scheduler -- python -m job_alert --config /app/config.yaml

# Generate output\digest.html without sending
docker compose --profile tools run --rm dry-run

# Pull an updated image and recreate the service
docker compose pull
docker compose up -d

# Stop without deleting history
docker compose down
```

Override schedule settings in `.env` if wanted:

```dotenv
JOB_ALERT_TIMEZONE=Africa/Lagos
JOB_ALERT_TIMES=07:07,19:07
RUN_ON_START=true
```

Back up the named volume before resetting it:

```powershell
docker run --rm -v job-alert_job-alert-data:/data -v "${PWD}:/backup" alpine tar czf /backup/job-alert-data.tgz -C /data .
```

Deleting the volume resets sent-URL history and can cause duplicate alerts:

```powershell
docker compose down -v
```

## Local Python install

Python 3.12+ is required.

### uv

```bash
uv venv
uv pip install -e '.[dev]'
```

### pip

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Copy the environment template; never commit the resulting file:

```bash
cp .env.example .env
```

Fill these locally:

- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `DIGEST_TO` — optional; defaults to `GMAIL_ADDRESS`
- `JOOBLE_API_KEY` — optional, needed only for Jooble
- `APIFY_TOKEN` — optional, needed only for enabled actors

`.env` is ignored. The app never prints secrets and only loads `.env` for live runs. Fixture-backed dry runs and tests need no credentials.

## Gmail setup

1. Enable 2-Step Verification on the sending Google account.
2. Open Google Account → Security → App passwords.
3. Create an app password for this tool and put it in `.env` as `GMAIL_APP_PASSWORD` (not your normal password).
4. Gmail IMAP must be available for the account. The tool opens `INBOX` read-only, fetches with `BODY.PEEK[]`, and never marks, moves, or deletes messages.

Outgoing mail uses `smtp.gmail.com:465`, contains HTML plus plain text, and includes `X-Job-Digest: 1` so it cannot ingest its own digest.

## Configure sources and email alerts

Edit `config.yaml`:

- `roles.title_patterns`: keep this narrow; matching is title-only.
- `roles.exclude_title_terms`: defaults include `intern` and `internship`.
- `sources`: enable/disable each adapter; edit Greenhouse, Lever, and Ashby slugs, SmartRecruiters company identifiers, and Recruitee tenants.
- `alert_senders`: relevant only when `sources.gmail_alerts.enabled` is true. It is currently false, so the application does not read your inbox. Sender addresses must exactly match the alerts you actually receive.
- `max_jobs_per_email`: global unique-job cap.

If you later enable Gmail alert ingestion, create alerts on LinkedIn, Wellfound, Jobberman, MyJobMag, and Hot Nigerian Jobs for:

- Cloud Engineer / Cloud Architect
- DevOps Engineer
- Site Reliability Engineer / SRE

Combine the role alerts with terms such as `visa sponsorship`, `relocation support`, `remote worldwide`, or `work from anywhere`. Send them to the Gmail account in `.env`. Only exact addresses in `alert_senders` are considered. Verify LinkedIn's exact From address in one of your own messages and update the supplied example if needed. The parser uses bounded text from each alert card for company, location, and eligibility evidence; being delivered by a “visa” or “remote” search does not qualify a vacancy on its own. A matching email that yields no recognized job links appears by subject under **Unparsed alerts**.

### Save sample alert emails

Per-sender rules are deliberately explicit. To improve them with your actual templates:

1. In Gmail, open one alert from each board.
2. Choose **More → Download message**.
3. Remove or replace personal names, email addresses, tracking IDs, and private query parameters.
4. Save sanitized copies as `.eml` under `tests/fixtures/private/` (this directory is ignored).
5. Never commit unsanitized mail. Run the tests after adapting selectors/rules.

The current tests use synthetic sanitized MIME messages and cover every configured sender rule. Real `.eml` templates cannot be validated until you add samples.

## Run

Live run (one digest at most):

```bash
job-alert --config config.yaml
# or
python -m job_alert --config config.yaml
```

Dry run using public sources, with no send:

```bash
job-alert --dry-run
```

Fully offline, credential-free dry run from saved fixtures:

```bash
job-alert --dry-run --fixtures tests/fixtures
```

A dry run writes `digest.html`, sends nothing, and does not mark URLs or Message-IDs as delivered. If there are no new jobs and no unparsed alerts, a live run sends nothing. An unparsed-only run sends a diagnostic digest with a zero job count.

State lives in `.cache/job-alert/state.sqlite3`; UK sponsor data is cached in `.cache/job-alert/` and refreshed weekly. Back up the SQLite file if sent history matters. Deleting it intentionally resets URL and Message-ID history.

### Exit codes

- `0`: successful run, including no-news
- `2`: invalid configuration or missing live send credentials
- `3`: all attempted enabled sources failed
- `4`: SMTP send failed; nothing was marked sent

An individual source failure is logged and all other sources continue.

## Linux cron alternative

Do not run cron and the Docker scheduler at the same time unless duplicate delivery is acceptable. For a local Python installation, use absolute paths and schedule conservatively; Remotive recommends at most four API calls per day.

## Rule behavior

- Jobs older than 48 hours and canonical URLs already sent are dropped.
- A job is retained only when it has explicit vacancy-level evidence of visa sponsorship or relocation, or explicit fully remote/from-anywhere-in-the-world evidence.
- Generic `remote`, `global team`, `EMEA`, and `Africa` are not worldwide eligibility. Country/region, timezone, residency, work-authorization, payroll/entity, and “only” restrictions override worldwide-looking text.
- Sponsorship and relocation negatives are checked before their corresponding positive phrases. Unclear evidence does not qualify.
- Arbeitnow's structured `visa_sponsorship=true` response filter is trusted. A Jooble query term or email-alert query is not trusted as eligibility evidence.
- A normalized exact company match in the UK sponsor register upgrades the annotation from `unclear` to `likely`, but never qualifies a vacancy by itself; a sponsor licence does not mean that role will sponsor.
- A job may appear in both digest sections but consumes one unique-job slot and is marked sent once.
- URLs are marked sent only after SMTP success. A failed send loses no jobs.

## Tests and quality checks

All tests block network access:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy src
```

Parser tests use saved synthetic source responses. SMTP, IMAP, and HTTP boundaries are mocked or bypassed.

## Compliance

This project does not scrape LinkedIn. It does not implement custom page scrapers for LinkedIn, Wellfound, or Nigerian boards, bypass CAPTCHAs/bot protection/login walls, or automate account login. Those boards are covered only by alerts you elect to send to Gmail. Remote OK, Jobicy, Himalayas, SmartRecruiters, and Recruitee are accessed only through their public API/feed interfaces, with supplied links and attribution preserved where required. If a source or tenant cannot be accessed through its public API/feed or your allowlisted alert emails, it is ignored rather than scraped. Public API/RSS adapters should be scheduled conservatively.

Apify is off by default. **Check each target site's current terms and robots/access rules before enabling any actor.** Do not configure an actor for a prohibited or login-gated source. You are responsible for actor inputs, costs, and terms compliance.

## License

MIT

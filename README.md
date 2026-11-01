# SoilMate

SoilMate is a multilingual agricultural voice and chat assistant for Indian farmers. It combines an agentic Gemini workflow with live weather, gridded soil estimates, reported mandi quotes, and fetched official crop references. Every unavailable provider is shown as unavailable; missing measurements and schedules are never replaced with placeholder numbers.

## What works

- Typed chat with SSE progress, bounded execution, cancellation, request deduplication, and persisted tool traces.
- Gemini Live voice with microphone streaming, transcripts, PCM playback, barge-in, concurrent tools, tool cancellation, and explicit cleanup.
- Session history and editable farmer profiles, isolated by a signed browser cookie in hosted mode.
- Evidence-linked advisories and schedules. A schedule is saved only when every stage has an exact supporting quotation from a fetched official reference.
- Explicit source, retrieval time, coverage, freshness, and failure states.

## Architecture

```text
React/Vite UI
  |-- POST /api/chat/stream --------> FastAPI typed agent
  |-- WS /api/ws/live -------------> Gemini Live proxy
  |-- sessions/profile/history ----> SQLite
                                          |
                    +---------------------+----------------------+
                    |                     |                      |
               Open-Meteo          ISRIC SoilGrids       data.gov.in
               forecast            250 m estimate        mandi quotes
                    |
          fetched TNAU references (wheat and rice/paddy)
```

Typed and voice conversations use the same tools, evidence model, profile store, and advisory store.

## Data sources and limits

| Source | Use | Important limitation |
|---|---|---|
| [Open-Meteo](https://open-meteo.com/) | Seven-day model forecast | Forecasts are predictions. Threshold alerts are SoilMate heuristics, not official crop diagnoses. |
| [ISRIC SoilGrids](https://docs.isric.org/globaldata/soilgrids/) | 250 m gridded topsoil predictions | Not a field laboratory measurement. Missing or incomplete coverage returns `unavailable`. |
| [data.gov.in](https://data.gov.in/) | Reported APMC mandi quotes | Coverage, grade, transport costs, and arrival dates vary. Quotes older than three days are marked stale. |
| [TNAU wheat reference](https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html) | Regional wheat guidance | Applicability depends on state, variety, and planting method. |
| [TNAU rice reference](https://agritech.tnau.ac.in/govt_schemes_services/aas/paddy.html) | Regional rice/paddy guidance | Applicability depends on ecosystem, season, state, and method. |

Crop schedule references currently cover wheat and rice/paddy. Pest diagnosis and government-scheme eligibility verification remain unavailable until validated live integrations are added. Legacy advisories without recorded evidence are labelled in the UI.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Never commit `.env` files.

```env
GEMINI_API_KEYS=key1,key2
GEMINI_MODEL=gemini-2.5-flash
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
SARVAM_API_KEY=
DATA_GOV_API_KEY=
DB_PATH=
PORT=8000
FRONTEND_URL=http://localhost:5173
APP_MODE=local
SESSION_SECRET=
```

`APP_MODE=local` binds to loopback and retains the existing single-user demo history. For hosting, use `APP_MODE=hosted`, HTTPS, the exact frontend origin in `FRONTEND_URL`, and a stable random `SESSION_SECRET` of at least 32 characters. Hosted browser records use signed HTTP-only cookie isolation; this is ownership isolation, not account authentication.

## Run locally

Backend, from `SoilMate/backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Frontend, from `SoilMate/frontend`:

```powershell
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies HTTP and WebSocket traffic to `127.0.0.1:8000`.

## Verification

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q

cd ..\frontend
npm test
npm run build
```

The bounded real-provider check uses a temporary database and may consume API quota:

```powershell
cd backend
.\.venv\Scripts\python.exe integration_check.py
```

It checks weather, SoilGrids, mandi, both official crop references, one typed Gemini tool turn, and one Gemini Live audio turn without exposing credentials.

## Two-to-three-minute demo

1. Set the farm profile to Jaipur and choose a conversation language.
2. Ask for seven-day weather. Show live workflow events, expand Open-Meteo evidence, and show its source and retrieval time in Crop Advice.
3. Ask for a wheat schedule and provide variety/method details. Show the exact TNAU quotation in Planting Schedule. Unsupported stages remain unavailable.
4. Start Gemini Live, speak a question, interrupt the response, and show that the call continues. End the call and verify the microphone stops.
5. Open History, reload the session, and show restored messages, traces, profile, advisory, and schedule.
6. Demonstrate an unavailable provider response to show that SoilMate does not fabricate measurements.

## Deployment notes

Deploy FastAPI and the Vite build behind HTTPS with WebSocket and SSE support. Use one application worker unless process-local duplicate and active-turn guards are replaced with a shared store. SQLite suits the local hackathon demo; multi-instance hosting needs a managed database, account authentication, shared rate limiting, and monitoring.

### Render demo deployment

The included `render.yaml` and `Dockerfile` deploy the frontend and backend as one Render web service. The frontend uses the same origin for HTTP and WebSocket requests.

1. Push this repository, including `render.yaml`, `Dockerfile`, `.dockerignore`, and `.github/workflows/render-keep-alive.yml`, to GitHub.
2. In Render choose **New → Blueprint**, connect the repository, and deploy. Provide `GEMINI_API_KEYS`; add `SARVAM_API_KEY` and `DATA_GOV_API_KEY` if you use those providers. Render generates `SESSION_SECRET` and supplies the public URL and port automatically. Never commit your `.env` files.
3. Open the deployed `https://<service>.onrender.com/api/health` and confirm it responds. In GitHub, open **Settings → Secrets and variables → Actions → Variables** and add `RENDER_URL` with the service origin, for example `https://soilmate.onrender.com` (no `/api` path).
4. On the repository's default branch, enable GitHub Actions and manually run **Keep Render service awake** once to verify it. The scheduled workflow sends a request every 10 minutes. Check its run history for errors. It must be enabled in forks and may be disabled after inactivity on public repositories.

The ping is best effort: GitHub can delay or drop scheduled runs, and Render can restart or suspend a free service. The free workspace allowance is 750 instance hours per month shared across free services; a continuously running service uses up to 744 hours in a 31-day month. GitHub Actions usage limits may also apply. A paid Render web service avoids idle spin-down; Render-hosted cron jobs have a minimum monthly charge.

**History is not durable on the free Render service.** This app currently stores sessions, schedules, and profiles in SQLite on the local filesystem. Render can erase those files on a restart, redeploy, or spin-down, even with the scheduled ping. Use a paid Render service with a persistent disk and set `DB_PATH` to a file on that disk, or migrate the app to a managed database, before relying on saved data. The cron job is not a backup.

The current implementation is demo-ready based on working Gemini typed and live voice checks. It is not a general public production service: SoilGrids/data.gov.in availability varies, crop reference coverage is limited, and hosted identity uses browser ownership rather than user accounts.

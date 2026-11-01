# 🌱 SoilMate

> **Real-Time Multilingual Agronomic Advisory & Protective Planning Engine for Indian Farmers**

SoilMate is an autonomous agronomic AI assistant engineered for Indian agriculture. It delivers real-time voice and typed advisory by orchestrating **Google Gemini 3.5 Flash** reasoning, **Gemini 3.1 Flash Live** full-duplex conversational voice, and zero-mock real-time APIs (Open-Meteo weather forecasts, ISRIC SoilGrids topsoil measurements, Agmarknet mandi commodity rates, and official ICAR/TNAU crop agronomic references).

---

## ⚡ Key Capabilities

- **🎙️ Real-Time Gemini Live Voice (Sub-second Full-Duplex):**
  - Powered by `gemini-3.1-flash-live-preview` via Google's Bidirectional Live WebSocket (`wss://`).
  - Full-duplex 16kHz PCM streaming from farmer microphone directly to Gemini.
  - Native 24kHz audio synthesis using the warm, empathetic `Aoede` voice persona (*Priya*).
  - True real-time barge-in (interruption) detection: speaking immediately silences model audio and re-directs the conversation.
  - Interactive 3D harmonic mesh sphere (`MeshSphere`) on an HTML5 canvas reacting dynamically to voice states.

- **🧠 Multi-Turn Autonomous ReAct Agent:**
  - Powered by `gemini-3.5-flash` with iterative multi-step tool execution (up to 8 turns).
  - Server-Sent Events (SSE) streaming (`POST /api/chat/stream`) reporting real-time execution telemetry (*"Fetching Open-Meteo weather..."*, *"Querying SoilGrids WCS..."*, *"Checking mandi modal rates..."*).
  - Request deduplication and turn guards to prevent race conditions during rapid typing or speaking.

- **🌐 11 Indian Languages with Automatic Language Retention:**
  - Supports **Hindi (हिन्दी)**, **Telugu (తెలుగు)**, **Tamil (தமிழ்)**, **Marathi (मराठी)**, **Punjabi (ਪੰਜਾਬੀ)**, **Bengali (বাংলা)**, **Gujarati (ગુજરાતી)**, **Kannada (ಕನ್ನಡ)**, **Malayalam (മലയാളം)**, **Odia (ଓଡ଼ିଆ)**, and **English**.
  - **Automatic Spoken Language Detection:** Listens to the farmer's spoken language, dynamically matches it, and maintains that language across conversational turns.
  - Indian language STT/TTS powered by Sarvam AI (*Saaras v2* & *Bulbul v3*) with graceful browser Web Speech API fallback.

- **🛡️ Zero-Mock Data Guarantee:**
  - Every data point originates from validated live sources. Missing coverage states are reported explicitly as `unavailable`; measurements and sowing schedules are never hallucinated or replaced with dummy values.
  - Schedule recommendations strictly quote supporting excerpts from official agricultural references (ICAR & TNAU).

- **💾 Persistent Farmer Profile & Conversational Memory:**
  - Asynchronous SQLite database (`aiosqlite`) storing sessions, full multi-turn message histories with tool execution traces, farmer profiles, and generated planting advisories.
  - Cross-origin session tracking via signed ownership tokens and `X-Soilmate-Owner` headers, immune to third-party cookie restrictions.

---

## 🏗️ Architecture

```
                      ┌───────────────────────────────────────────────┐
                      │              SoilMate Frontend                │
                      │  React 18 + Vite + Tailwind CSS + Web Audio   │
                      │            (Hosted on Vercel)                 │
                      └───────┬───────────────────────────────┬───────┘
                              │ HTTP / SSE                    │ Bidirectional WebSocket
                              │ (Chat, History, Tools)        │ (16kHz in / 24kHz out)
                              ▼                               ▼
                      ┌───────────────────────────────────────────────┐
                      │             FastAPI Application               │
                      │          (Hosted on Render Backend)           │
                      └───────┬───────────────────────────────┬───────┘
                              │                               │
             ┌────────────────┴───────────────┐               │
             ▼                                ▼               ▼
   ┌───────────────────┐            ┌───────────────────┐ ┌──────────────────────┐
   │ ReAct Agent Core  │            │ Live Data Engine  │ │ Gemini Live WS       │
   │ gemini-3.5-flash  │            │  (Real Data Only) │ │ gemini-3.1-flash-live│
   │ • Prompts & Turns │            │ • Open-Meteo      │ │ • Sub-second Voice   │
   │ • Auton. Tools    │            │ • ISRIC SoilGrids │ │ • Native Audio (Aoede│
   │ • SQLite History  │            │ • Agmarknet Mandi │ │ • Live barge-in      │
   └───────────────────┘            │ • Sarvam AI TTS   │ │ • Live tool streaming│
                                    └───────────────────┘ └──────────────────────┘
```

---

## 📡 Live Data Integrations

| Provider | Data Extracted | Purpose & Limitations |
| :--- | :--- | :--- |
| **[Open-Meteo](https://open-meteo.com/)** | 7-day hourly & daily forecast, precipitation, wind speed, relative humidity, UV index | Generates agricultural alerts (heavy rainfall, frost, heat stress). Heuristic alerts, not official agro-meteorological advisories. |
| **[ISRIC SoilGrids](https://docs.isric.org/globaldata/soilgrids/)** | WCS 2.0.1 GeoTIFF coverage: pH, sand, silt, clay, SOC, nitrogen | 250 m gridded physical/chemical topsoil estimates for 0–5 cm depth. Physical soil testing is advised for input prescriptions. |
| **[data.gov.in](https://data.gov.in/)** | Live APMC Agmarknet commodity market prices | Real-time modal, min, and max mandi market rates across Indian states. Quotes older than 3 days are marked stale. |
| **[TNAU & ICAR](https://agritech.tnau.ac.in/)** | Comprehensive agronomic guides (wheat, rice/paddy) | Validates critical crop stages (CRI, tillering, flowering, grain filling). Requires exact quotation matching for schedule saving. |
| **[Sarvam AI](https://www.sarvam.ai/)** | Saaras v2 STT, Bulbul v3 TTS, Mayura translation | High-accuracy Indic voice recognition, emotional speech synthesis (*Priya*), and script normalization. |

---

## 🚀 Deployment Guide (Unified Single Render Web Service)

SoilMate can be hosted **entirely as a single unified Web Service on Render** (`https://soilmate.onrender.com`), serving both the React frontend and FastAPI backend on the same domain with **zero CORS issues, 1st-party cookies, and instant sub-second WebSocket audio**.

You can deploy using either **Docker (Recommended)** or the **Native Python runtime**.

---

### Option A: Docker Deployment (Recommended — 1-Click / Blueprint)

Render automatically detects the root `Dockerfile` and `render.yaml` to build a multi-stage image (Node.js builds Vite frontend $\rightarrow$ Python 3.12 runs unified server):

1. In the [Render Dashboard](https://dashboard.render.com), click **New + $\rightarrow$ Web Service** (or use **Blueprints** with `render.yaml`).
2. Connect your SoilMate GitHub repository.
3. Select **Docker** as the Runtime:
   - **Root Directory:** *(leave blank / repository root)*
   - **Health Check Path:** `/api/health`
4. Under **Environment Variables**, configure:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `APP_MODE` | `hosted` | Enables production security & session cookies |
| `GEMINI_API_KEY` | `your-google-gemini-key` | [Get free from Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Reasoning engine for ReAct agent |
| `GEMINI_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Live multimodal WebSocket audio model |
| `SESSION_SECRET` | *(Optional random 32+ char string)* | Auto-generated deterministically if left empty |
| `SARVAM_API_KEY` | `your-sarvam-key` | *(Optional)* Indian language voice STT/TTS |
| `DATA_GOV_API_KEY` | `your-data-gov-key` | *(Optional)* Agmarknet live mandi rates |

5. Click **Create Web Service**! Render will build the frontend and backend together and serve everything at `https://soilmate.onrender.com`.

---

### Option B: Native Python Runtime on Render

If you prefer using Render's standard Python runtime (no Docker):

1. Create a **Web Service** on [Render](https://dashboard.render.com):
   - **Runtime:** `Python 3`
   - **Root Directory:** *(leave blank / repository root)*
   - **Build Command:** `./build.sh`
   - **Start Command:** `python run.py`
   - **Health Check Path:** `/api/health`
2. Add the environment variables listed in the table above.
3. Deploy! The `build.sh` script automatically builds the React frontend and installs all Python dependencies.

---

### Dual-Hosting Option (Render Backend + Vercel Frontend)

If you still prefer hosting frontend on Vercel separately:
1. **Render Backend:** Follow Option A or B above. Set `FRONTEND_URL=https://your-app.vercel.app`.
2. **Vercel Frontend:** Import repository with Root Directory `frontend`, set `VITE_API_BASE_URL=https://soilmate.onrender.com`. Single-page routing is handled by `frontend/vercel.json`.

---

## 💻 Local Development Setup

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm

### 1. Clone & Configure Environment

```powershell
git clone https://github.com/4941-Piyush/SoilMate.git
cd SoilMate
```

Create `backend/.env`:
```powershell
cp backend/.env.example backend/.env
```
Fill in your `GEMINI_API_KEY` in `backend/.env`.

### 2. Run Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```
Backend starts on `http://127.0.0.1:8000`.

### 3. Run Frontend

```powershell
cd ..\frontend
npm install
npm run dev
```
Frontend starts on `http://localhost:5173`. Vite automatically proxies `/api` and `/ws` to the local FastAPI server.

---

## 🧪 Verification & Testing

Run backend tests:
```powershell
cd backend
pytest tests -v
```

Run frontend build verification:
```powershell
cd ..\frontend
npm run build
```

Run end-to-end integration check (consumes live provider calls):
```powershell
cd ..\backend
python integration_check.py
```

---

## 📂 Project Structure

```
SoilMate/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI entrypoint, SSE streaming, and WebSocket bridge
│   │   ├── config.py                   # Pydantic environment settings
│   │   ├── security.py                 # Cross-origin origin checks, session signing, HMAC
│   │   ├── agent/
│   │   │   ├── orchestrator.py         # Multi-turn Gemini 3.5 Flash ReAct agent loop
│   │   │   ├── tools.py                # Live tool definitions and execution dispatcher
│   │   │   ├── advisories.py           # Advisory persistence & ICAR quotation validator
│   │   │   ├── prompts.py              # System prompts & agronomic instructions
│   │   │   └── turns.py                # Request deduplication and turn concurrency guards
│   │   ├── db/
│   │   │   ├── database.py             # SQLite aiosqlite connection pool & migrations
│   │   │   └── repository.py           # CRUD for sessions, messages, profiles, and advisories
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic request/response schemas
│   │   └── services/
│   │       ├── gemini_live.py          # Gemini 3.1 Flash Live bidirectional audio WebSocket proxy
│   │       ├── gemini_pool.py          # Gemini API key pool manager with automatic failover
│   │       ├── language.py             # Unicode script detection & spoken language resolution
│   │       ├── weather.py              # Open-Meteo 7-day forecast & alert calculations
│   │       ├── soil.py                 # ISRIC SoilGrids WCS 2.0.1 GeoTIFF parser (with Pillow fallback)
│   │       ├── mandi.py                # Agmarknet APMC live mandi commodity market rates
│   │       ├── voice.py                # Sarvam AI Saaras STT & Bulbul TTS synthesis
│   │       └── translation.py          # Indic neural translation with gender-alignment
│   ├── requirements.txt
│   └── run.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # Top-level state (language, profile, layout)
│   │   ├── components/
│   │   │   ├── VoiceAssistant.jsx      # Animated 3D harmonic mesh sphere & voice orb
│   │   │   ├── ChatPanel.jsx           # Chat container, live voice proxy, message history
│   │   │   ├── ChatMessages.jsx        # Rich chat bubbles with audio playback & tool traces
│   │   │   ├── ChatInput.jsx           # Typing field, quick chips, and voice note recorder
│   │   │   ├── DashboardPanel.jsx      # Tabbed agronomic dashboard (Advice, Calendar, Profile)
│   │   │   ├── LanguageSelector.jsx    # 11 Indian language picker
│   │   │   └── LocationInput.jsx       # Geocoding search & farm location picker
│   │   ├── hooks/
│   │   │   ├── useGeminiLive.js        # Full-duplex Web Audio WebSocket pipeline
│   │   │   └── useSpeech.js            # Browser speech recognition fallback
│   │   ├── services/
│   │   │   └── api.js                  # Unified API client with cross-origin session tracking
│   │   └── utils/
│   │       ├── translations.js         # Complete UI translation dictionary for 11 languages
│   │       └── audioManager.js         # Single-playback global audio controller
│   ├── vercel.json                     # Vercel SPA rewrite rules
│   ├── package.json
│   └── vite.config.js
└── README.md
```

---

## 📄 License

This project is licensed under the Apache 2.0 License.

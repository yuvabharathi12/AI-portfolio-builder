# ✦ Resume → Portfolio Generator

Upload a resume → AI reads it deeply → decides what sections to create → generates a beautiful portfolio site.

## Stack (all free)
| Layer     | Tool          | Why                          |
|-----------|---------------|------------------------------|
| Frontend  | **Streamlit** | Zero-config Python UI        |
| Backend   | **FastAPI**   | Fast async API               |
| Database  | **SQLite**    | File-based, zero setup       |
| AI        | **Groq**      | Free tier, ultra-fast LLaMA  |

---

## Setup

### 1. Install deps
```bash
pip install -r requirements.txt
```

### 2. Set API key
```bash
export GROQ_API_KEY=gsk_...
```

### 3. Run FastAPI backend (terminal 1)
```bash
uvicorn backend.main:app --reload --port 8000
```

### 4. Run Streamlit frontend (terminal 2)
```bash
streamlit run frontend/app.py
```

### 5. Open browser
- Streamlit UI: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs

---

## What the AI does (not a fixed template)

Instead of always generating `About / Skills / Projects`, the AI:

1. **Reads the full resume** — career arc, tone, achievements
2. **Decides section types** — researcher? → publications+methodology. Designer? → case studies. Student? → learning trajectory
3. **Picks section names creatively** — "What I Build" vs "Projects", "How I Think" vs "About"
4. **Chooses a color theme** — slate, ocean, forest, rose, amber, or violet based on vibe
5. **Writes in first person** — warm, professional, with real numbers

---

## 🚀 Deployment (Free Tier)

### 1. Deploy Backend (FastAPI) on [Render](https://render.com)
1. **New Web Service** → Connect your GitHub Repo.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port 10000`
4. **Environment Variables:**
   - `GROQ_API_KEY`: Your key from [Groq Cloud](https://console.groq.com/keys)
5. **Copy the URL** Render gives you (e.g., `https://ai-portfolio-backend.onrender.com`).

### 2. Deploy Frontend (Streamlit) on [Streamlit Community Cloud](https://streamlit.io/cloud)
1. **New App** → Connect your GitHub Repo.
2. **Main file:** `app.py`
3. **Advanced Settings (Secrets):** Add your backend URL:
   ```toml
   API_URL = "https://your-backend-url.onrender.com"
   ```
4. **Deploy!**

---

## API Endpoints

| Method | Path                        | Description                   |
|--------|-----------------------------|-------------------------------|
| POST   | `/upload`                   | Upload resume, get portfolio  |
| GET    | `/portfolio/{id}`           | Get portfolio HTML            |
| GET    | `/portfolios`               | List all portfolios           |
| GET    | `/health`                   | Health check                  |

---

## File structure
```
resume_portfolio/
├── backend/
│   └── main.py          ← FastAPI app + AI logic
├── frontend/
│   └── app.py           ← Streamlit UI
├── db/
│   └── portfolios.db    ← SQLite (auto-created)
├── requirements.txt
└── README.md
```

---

## Extending

**Add a new section type:**
1. Add JSON shape to `SYSTEM_PROMPT` in `backend/main.py`
2. Add `render_section` handler for the new `type`

**Add a new theme:**
Add entry to `THEMES` dict in `backend/main.py`

**Deploy free:**
- Backend → Railway / Render (free tier)
- Frontend → Streamlit Cloud (free)
- DB → stays SQLite (or swap to Turso for edge SQLite)

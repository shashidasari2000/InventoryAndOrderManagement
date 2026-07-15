# Inventory and Order Management (Backend)

FastAPI backend for inventory, supplier orders, buyer orders/POS, invoicing, and related accounting APIs.

## Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in secrets
alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# or: uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/health`  
API docs: `http://localhost:8000/api/docs`  
API prefix: `/api/v1/...`

## Deploy on Vercel (backend only)

1. Create a new project in Vercel and import  
   `https://github.com/shashidasari2000/InventoryAndOrderManagement.git`
2. Framework preset: **Other** (or let Vercel detect Python).
3. Root directory: leave as repo root (this backend *is* the repo root).
4. Add **Environment Variables** (Production):

| Name | Example / notes |
|------|------------------|
| `DATABASE_URL` | Neon URL with `?sslmode=require` (use **pooled** URL if Neon shows one) |
| `SECRET_KEY` | Long random string |
| `ENCRYPTION_KEY` | Valid Fernet key (base64) |
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| Optional AI keys | `GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, etc. |
| WhatsApp | Only if you use WhatsApp webhooks |

5. Deploy. After deploy, test:
   - `https://YOUR_PROJECT.vercel.app/health`
   - `https://YOUR_PROJECT.vercel.app/api/docs`

6. Point the **mobile app** base URL to `https://YOUR_PROJECT.vercel.app`  
   (API routes remain under `/api/v1/...`).

### Notes for mobile + Vercel

- CORS is already open (`allow_origins=["*"]`) for mobile clients.
- Vercel runs FastAPI as a **serverless** function (cold starts possible).
- Prefer Neon’s **connection pooler** host for serverless.
- Do **not** commit `.env`; set secrets only in Vercel project settings.
- Migrations are not run by Vercel automatically — run `alembic upgrade head` locally against Neon when schema changes.

## Stack

- FastAPI + SQLAlchemy + Alembic  
- PostgreSQL (Neon or other) via `DATABASE_URL`

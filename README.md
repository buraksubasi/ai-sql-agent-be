# AI SQL Agent

Doğal dille veritabanı sorgulama yapabilen, Türkçe konuşan bir AI asistan uygulaması. Kullanıcı sorularını LangChain SQL Agent aracılığıyla PostgreSQL sorgularına dönüştürür; genel konuşmalar için Gemini ile yanıt üretir.

---

## Mimari

```
Tarayıcı (Next.js UI)
    │  POST /api/chat/stream
    ▼
Next.js API Route (SSE proxy)
    │  POST {BACKEND_API_URL}/api/chat/stream
    ▼
FastAPI Backend (Python)
    ├── Intent Router (Gemini)
    │       ├── DB  → LangChain SQL Agent → Neon PostgreSQL
    │       └── GENERAL → Gemini Chat (+ isteğe bağlı DuckDuckGo araması)
    └── SSE: thinking | token | done | error
```

---

## Backend

### Klasör Yapısı

```
ai-sql-agent-be/
├── main.py            # FastAPI uygulaması, CORS, API route'ları
├── agent.py           # SQL Agent Router, oturum hafızası, streaming
├── database.py        # Neon PostgreSQL bağlantısı (LangChain SQLDatabase)
├── requirements.txt   # Python bağımlılıkları
├── Dockerfile         # Python 3.12-slim tabanlı container
├── docker-compose.yml # Yerel geliştirme / deployment
└── .env               # Gizli anahtarlar (git'e commit edilmez)
```

### Teknoloji Stack'i

| Katman | Teknoloji |
|--------|-----------|
| Dil | Python 3.12 |
| Web Framework | FastAPI |
| ASGI Sunucu | Uvicorn |
| Validasyon | Pydantic |
| AI / LLM | Google Gemini (`gemini-2.5-flash`) |
| Agent Framework | LangChain (`langchain`, `langchain-core`, `langchain-community`) |
| SQL Agent | `create_sql_agent` + `SQLDatabaseToolkit` |
| Web Arama | DuckDuckGo (`ddgs` / `DuckDuckGoSearchRun`) |
| Veritabanı | PostgreSQL — Neon (serverless) |
| ORM / DB Bağlantısı | SQLAlchemy + `psycopg2-binary` |
| Konfigürasyon | `python-dotenv` |
| Containerization | Docker + Docker Compose |

### API Endpoint'leri

| Method | Path | Request Body | Açıklama |
|--------|------|--------------|----------|
| `POST` | `/api/chat` | `{ "question": string, "session_id"?: string }` | Senkron yanıt — JSON `{ "answer": string }` döner |
| `POST` | `/api/chat/stream` | `{ "question": string, "session_id"?: string }` | SSE streaming — gerçek zamanlı chunk'lar gönderir |

**SSE Chunk Tipleri (`/api/chat/stream`):**

| Tip | Açıklama |
|-----|----------|
| `thinking` | Agent'in düşünme adımları (niyet analizi, araç çağrıları, arama) |
| `token` | Yanıt metni |
| `done` | Stream tamamlandı |
| `error` | Hata mesajı |

### Agent Mantığı

1. **Intent Router** — Kullanıcı mesajı Gemini ile `DB` veya `GENERAL` olarak sınıflandırılır.
2. **DB modu** — LangChain SQL Agent, Neon PostgreSQL şemasını okur, SQL üretir ve çalıştırır, sonucu doğal dile çevirir.
3. **GENERAL modu** — Gemini ile doğrudan yanıt verilir. Güncel bilgi gerekiyorsa DuckDuckGo araması yapılır ve sonuç prompt'a eklenir.
4. **Oturum Hafızası** — `session_id` bazlı in-memory sohbet geçmişi (sunucu yeniden başlatıldığında sıfırlanır).

### Ortam Değişkenleri

| Değişken | Açıklama |
|----------|----------|
| `NEON_DATABASE_URL` | Neon PostgreSQL bağlantı URL'i (SSL zorunlu) |
| `GOOGLE_API_KEY` | Google Gemini API anahtarı |

### Kurulum ve Çalıştırma

**Docker Compose ile:**
```bash
# .env dosyasını oluştur ve değişkenleri doldur
cp .env.example .env

docker compose up --build
```
Uygulama `http://localhost:8002` adresinde çalışır (container içinde port 8000).

**Doğrudan Python ile:**
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Otomatik API dokümantasyonu: `http://localhost:8000/docs`

---

## Frontend

### Klasör Yapısı

```
ai-sql-agent-fe/
├── src/
│   ├── app/
│   │   ├── page.tsx                    # Ana sayfa
│   │   ├── layout.tsx                  # Root layout, metadata, fontlar
│   │   ├── globals.css                 # Global stiller + Tailwind
│   │   ├── api/chat/stream/route.ts    # SSE proxy (Next.js API Route)
│   │   └── actions/chat.ts             # Server action (non-streaming)
│   └── components/
│       └── ChatInterface.tsx           # Ana chat bileşeni (SSE, UI)
├── .env.local                          # Backend URL ortam değişkeni
├── next.config.ts
├── tsconfig.json
└── package.json
```

### Teknoloji Stack'i

| Katman | Teknoloji |
|--------|-----------|
| Dil | TypeScript |
| Framework | Next.js 16.2.9 (App Router) |
| UI Kütüphanesi | React 19.2.4 |
| Stil | Tailwind CSS v4 |
| Fontlar | Geist Sans & Geist Mono (`next/font/google`) |
| Linting | ESLint 9 + `eslint-config-next` |
| Build Aracı | Turbopack (Next.js varsayılan) |

### Bileşenler

| Bileşen | Dosya | Açıklama |
|---------|-------|----------|
| `ChatInterface` | `src/components/ChatInterface.tsx` | Ana chat UI; SSE parse, mesaj listesi, input alanı, örnek promptlar |
| `ThinkingSection` | `ChatInterface.tsx` içinde | Agent'in düşünme adımlarını gösteren açılır/kapanır panel |
| `renderInline` | `ChatInterface.tsx` içinde | `**bold**` ve `` `code` `` için hafif markdown render yardımcısı |

### Özellikler

- Gerçek zamanlı SSE streaming (düşünme adımları + yanıt metni)
- `session_id` ile oturum sürekliliği (UUID, mount'ta üretilir)
- İlk yüklemede örnek prompt chip'leri
- Dark mode desteği (`prefers-color-scheme`)
- Enter ile gönder, Shift+Enter ile satır atlama

### Ortam Değişkenleri

| Değişken | Açıklama |
|----------|----------|
| `BACKEND_API_URL` | Backend API adresi (varsayılan: `http://127.0.0.1:8000`) |

**`.env.local` örneği:**
```
BACKEND_API_URL=http://localhost:8002
```

### Kurulum ve Çalıştırma

```bash
cd ai-sql-agent-fe

npm install
npm run dev
```

Uygulama `http://localhost:3000` adresinde açılır.

**Production build:**
```bash
npm run build
npm start
```

---

## Deployment

| Servis | Platform |
|--------|----------|
| Backend | [Render](https://render.com) (`https://ai-sql-agent-be.onrender.com`) |
| Frontend | Next.js destekleyen herhangi bir platform (Vercel, Render, vb.) |
| Veritabanı | [Neon](https://neon.tech) (serverless PostgreSQL) |

---

## Lisans

MIT

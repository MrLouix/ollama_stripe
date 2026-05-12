# Ollama SaaS Gateway

**Status:** 🚧 Specification phase — implementation in progress

A self-hosted API gateway that monetizes local Ollama LLM instances. Exposes Ollama behind an OpenAI-compatible API with authentication, quotas, multi-tenant support, and Stripe billing.

## 🎯 Vision

"Ollama SaaS in a Box" — Turn your local Ollama instance into a commercial API with:
- 🔐 **Authentication**: Bearer API keys with SHA-256 hashing
- 📊 **Quotas & Rate Limiting**: RPM, daily/monthly token limits
- 💳 **Billing**: Native Stripe integration (subscriptions + metered usage)
- 🏢 **Multi-tenant**: Isolated tenants with per-tenant model access
- 🔌 **OpenAI-compatible**: Works with existing tools (n8n, LibreChat, Open WebUI)
- 🐳 **Docker Compose**: One-click deployment

## 🏗️ Architecture

```
Client → HTTPS → Caddy (reverse proxy)
                    ↓
              FastAPI Gateway (auth/quotas/logging)
                 ↓           ↓            ↓
            PostgreSQL     Redis       Ollama (localhost:11434)
         (tenants, keys,  (rate limit,  (never exposed publicly)
          plans, usage)    counters)
```

**Key principle**: Ollama binds to `127.0.0.1:11434` only — all public access goes through the authenticated gateway.

## 📦 Tech Stack

- **Backend**: FastAPI (Python), async
- **Database**: PostgreSQL (tenants, API keys, plans, usage tracking)
- **Cache**: Redis (rate limiting, quota counters)
- **Reverse Proxy**: Caddy (auto-HTTPS)
- **Billing**: Stripe (subscriptions + usage records)
- **Deployment**: Docker Compose (6 services)

## 🚀 Quick Start (Coming Soon)

```bash
# 1. Clone
git clone https://github.com/MrLouix/ollama_stripe.git
cd ollama_stripe

# 2. Configure
cp .env.example .env
# Edit .env with your Stripe keys, domain, etc.

# 3. Launch
docker compose up -d

# 4. Initialize database
docker compose exec gateway alembic upgrade head

# 5. Create admin user
docker compose exec gateway python -m app.cli create-admin \
  --email admin@example.com --password yourpassword

# 6. Pull an Ollama model
docker compose exec ollama ollama pull llama3
```

## 📋 Current Status

### ✅ Completed
- [x] Detailed specification (`docs/spec.md`)
- [x] Implementation plan with unit tests (`docs/plan.md`)
- [x] Architecture design
- [x] Data model (11 PostgreSQL tables)
- [x] API contract (OpenAI-compatible)

### 🚧 In Progress
- [ ] FastAPI application skeleton
- [ ] Database models and migrations
- [ ] Authentication service (API keys + JWT)
- [ ] Rate limiting (Redis)
- [ ] Ollama client and `/v1/chat/completions` endpoint

### 📅 Roadmap

**V1 (MVP)**
- Auth via Bearer API keys
- `POST /v1/chat/completions` (non-streaming)
- Multi-tenant with isolation
- Quotas (RPM, daily, monthly)
- Admin CRUD endpoints
- Stripe subscriptions (fixed plans)
- Docker Compose deployment

**V1.1**
- Streaming (SSE)
- Metered usage records to Stripe
- Email alerts for quota thresholds
- CSV export

**V2**
- Multi-Ollama routing (by model, cost, load)
- Advanced RBAC
- SSO for operators
- Content moderation policies

## 🎯 Differentiation

| Project | Auth | Quotas | Billing | Multi-tenant | Ollama-first |
|---------|------|--------|---------|--------------|--------------|
| ollama-auth-proxy | ✅ | ❌ | ❌ | ❌ | ✅ |
| llmgateway | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| **This project** | ✅ | ✅ | ✅ Stripe | ✅ | ✅ |

## 📖 Documentation

- **Specification** (French): `docs/spec.md` — comprehensive technical spec
- **Implementation Plan**: `docs/plan.md` — 8 phases with code examples and unit tests
- **Research**: `docs/historique.md` — market analysis and competitive landscape

## 🤝 Contributing

This project is in active specification/implementation phase. Contributions welcome once V1 core is established.

## 📄 License

MIT License — see LICENSE file (to be added)

## 🔗 Links

- **GitHub**: https://github.com/MrLouix/ollama_stripe
- **Ollama**: https://ollama.com
- **Stripe Docs**: https://stripe.com/docs/billing

---

**Note**: This README will be updated as implementation progresses. Current focus: Phase 0-2 (infrastructure + auth).

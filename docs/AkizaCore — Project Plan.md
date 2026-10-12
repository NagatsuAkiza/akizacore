# AkizaCore — Project Plan

_AI Discord Assistant multifungsi · Draft v1 · 12 Okt 2026 · Dev di laptop lokal, VPS menyusul_

## 1. Project Overview

**Tujuan:** platform asisten Discord, bukan sekadar command bot: modul AI, ekonomi, hiburan, utility, moderasi, dan konfigurasi, lengkap dengan database, API, dashboard, dan manajemen user.

**Target pengguna:** member server (AI, level/koin, reminder), admin/moderator (moderasi, log, konfigurasi tanpa coding), pemilik komunitas (analytics, kontrol fitur dan biaya AI).

**Use case utama:** tanya jawab dengan AI; ekonomi dan level sebagai insentif keaktifan (koin juga menjadi bayaran fitur AI); utility pribadi; moderasi otomatis; konfigurasi server lewat dashboard.

**Scalability:** semua data ber-`server_id` (multi-server sejak awal); modul bisa dinyalakan per server (dasar tier premium); bot, API, dan worker bisa dipisah proses; sharding discord.py; multi-provider AI lewat satu interface.

## 2. System Architecture

| Layer | Tugas | Teknologi |
| --- | --- | --- |
| Discord Bot | Gateway, slash command, event, embed/tombol | discord.py |
| Service | Logika bisnis, dipakai bot DAN API | Python murni (tanpa import discord) |
| Backend API | REST untuk dashboard, auth, validasi | FastAPI |
| Database | Data utama, migrasi | PostgreSQL, SQLAlchemy async, Alembic |
| Cache/Queue | Cooldown, rate limit, short-term memory | Redis (mulai fase 3-4, belum wajib di MVP) |
| AI Processing | Orchestrator, agents, tools, memory, provider | modul `ai/` (bagian 13) |
| Dashboard | UI admin dan user | React + Vite + TS + Tailwind |

**Keputusan kunci:** bot dan API satu codebase, dua proses, berbagi Service Layer. Bot memanggil service langsung (bukan HTTP ke API sendiri) supaya cepat dan sederhana; API khusus untuk dashboard.

```
Discord User → Gateway → Bot (cog) → Service → Repository → PostgreSQL
                                  ↘ AI Orchestrator → Provider AI / Tools
Dashboard → FastAPI (auth, validasi) → Service → Repository → PostgreSQL
Hasil → Service → Bot (embed/respons) → Discord User
```

**Mode laptop sekarang:** tiga proses lokal (bot, `uvicorn` API, `npm run dev`) + PostgreSQL via Docker Compose atau Supabase gratis. Redis ditunda; pakai cache in-memory dulu.

## 3. Folder Structure

```
akizacore/
├── pyproject.toml          # dependensi + ruff/mypy/pytest
├── docker-compose.yml      # postgres (+ redis nanti)
├── alembic/                # migrasi database
├── src/akizacore/
│   ├── main.py             # entrypoint bot
│   ├── config/             # settings (pydantic-settings), baca .env
│   ├── core/               # kelas bot, loader cog, logging, exception, permission
│   ├── database/           # engine, session, repository (satu-satunya yang query)
│   ├── models/             # model SQLAlchemy (bentuk tabel)
│   ├── schemas/            # DTO Pydantic (data masuk/keluar)
│   ├── services/           # aturan bisnis: potong koin, level, warn (tanpa Discord)
│   ├── ai/                 # orchestrator, agents, tools, memory, providers
│   ├── cogs/               # ai/ economy/ fun/ utility/ moderation/ settings/ (lapisan tipis)
│   ├── api/                # FastAPI: app, routers, deps, auth
│   └── utils/              # helper murni tanpa state
├── dashboard/              # React + Vite + TS + Tailwind
└── tests/                  # unit (services) dan integrasi
```

## 4. Feature Planning

| Modul | MVP | V2 | Advanced |
| --- | --- | --- | --- |
| AI | Chat (`/ask`, mention), multi-turn, translation | Memory, preference learning, summarize chat, image prompt | Command suggestion, multi-agent |
| Economy | Balance, daily, XP/level, leaderboard, ledger | Work, shop, inventory, transfer (dengan batas) | Event musiman, pasar antar user |
| Fun | Meme, joke, reaction, poll | Games, personality test, meme generator | Music (butuh voice + hosting kuat) |
| Utility | Reminder, timer, server stats, user info | Notes, todo, weather, search | Calendar (OAuth) |
| Moderation | Warn, kick/ban/timeout, logging | Anti-spam, anti-link, automod, dashboard moderasi | Eskalasi otomatis |
| Settings | Config server, channel, feature toggle | Permission per command/role | Prefix, template konfigurasi |

**Model AI:** dua kelas lewat satu interface `LLMProvider` (format OpenAI-compatible): model cepat/murah untuk chat harian dan klasifikasi intent, model lebih kuat untuk ringkasan dan planning, plus model embedding kecil untuk memory. Groq, Gemini, atau OpenRouter bisa ditukar lewat konfigurasi. Batas free tier sering berubah, cek dokumen penyedia sebelum menetapkan harga koin.

**Conversation history:** tabel `conversations` (per user + channel) dan `messages` (role, isi, token). Konteks = N pesan terakhir + ringkasan bergulir untuk bagian lama. Cache aktif di memori/Redis, persist ke PostgreSQL, retensi bisa diatur (mis. 30 hari), user bisa `/forget`.

**Personality:** prompt berlapis: (1) persona inti global, (2) override per server (`settings.ai_persona`: nama, gaya, topik terlarang), (3) preferensi user (bahasa, panjang jawaban). Tersimpan di database dan bisa diedit dari dashboard.

## 5. Database Design

**Relasi:** `users` 1-1 `user_profiles`; `servers` 1-1 `settings`; `users` dan `servers` terhubung lewat `economy` (data per server) yang punya banyak `transactions` dan `inventory`; `conversations` 1-\* `messages`; `users` 1-\* `memories`, `reminders`; `servers`/`users` 1-\* `warnings`, `moderation_log`.

| Tabel | PK | FK | Kolom penting |
| --- | --- | --- | --- |
| users | id (ID Discord) | - | username, avatar, created_at |
| servers | id (guild ID) | - | name, owner_id, is_active |
| user_profiles | user_id | users.id | language, timezone, ai_prefs, ai_opt_out |
| settings | server_id | servers.id | log_channel_id, welcome_channel_id, autorole_id, ai_persona, features (JSONB) |
| commands | id | server_id (null = default) | name, enabled, allowed_roles, cooldown_s |
| conversations | id (UUID) | server_id, user_id | channel_id, summary, last_active_at |
| messages | id | conversation_id | role, content, tokens |
| memories | id | user_id, server_id | kind, content, embedding (pgvector), deleted_at |
| economy | (server_id, user_id) | servers.id, users.id | balance, xp, level, last_daily |
| transactions | id | server_id, user_id | amount (+/-), kind, balance_after, meta (ledger append-only) |
| shop_items / inventory | id | server_id, item_id, user_id | name, price, stock / quantity |
| warnings | id | server_id, user_id, mod_id | reason, active, created_at |
| moderation_log | id | server_id | target_id, mod_id, action, reason |
| reminders | id | user_id | channel_id, message, remind_at, status |

**Catatan:** ekonomi per server (sesuai bot sekarang); index `(server_id, user_id)` di tabel multi-server; `reminders(remind_at)` untuk status pending; index HNSW untuk `memories.embedding`; data lama SQLite dimigrasi sekali lewat skrip.

## 6. Development Roadmap

Asumsi: satu developer, dev di laptop, ±1 fase per minggu di bulan pertama.

| Fase | Isi | Selesai bila |
| --- | --- | --- |
| 1. Fondasi | Repo, pyproject, ruff/mypy/pytest, config, bot core, slash command, porting cog lama | Semua command lama jalan di struktur baru |
| 2. Database + user | PostgreSQL, SQLAlchemy async, Alembic, repository/service, onboarding guild, server settings, migrasi SQLite | Data di Postgres, `/setup` lewat service |
| 3. AI Assistant | Provider interface, `/ask`, history, persona, potong koin, kuota global | User ber-koin bisa chat dengan AI, kuota terkontrol |
| 4. Economy | Ledger, shop, inventory, work, anti-farming | Semua perubahan saldo tercatat di ledger |
| 5. Moderation | Automod, eskalasi warn, log lengkap | Aturan per server berjalan |
| 6. Dashboard | FastAPI + login Discord + halaman React | Admin ubah setting dari web |

## 7. React Dashboard Planning

**Stack:** React, Vite, TypeScript, Tailwind, React Router, TanStack Query; tipe API digenerate dari OpenAPI FastAPI. **Login:** Discord OAuth2; backend menukar code lalu membuat sesi cookie httpOnly. Daftar server hanya yang kamu punya izin Manage Server dan ada bot-nya.

| Grup       | Halaman                                                                      |
| ---------- | ---------------------------------------------------------------------------- |
| Auth       | Login with Discord, callback                                                 |
| Dashboard  | Overview, Server list, Analytics (aktivitas, pemakaian AI)                   |
| AI         | Conversation history, Personality (editor + preview), Memory (lihat/hapus)   |
| Economy    | User statistics, Currency management (adjust saldo tercatat di ledger), Shop |
| Moderation | Logs, Warnings, Auto moderation settings                                     |
| Settings   | Commands, Permission, Channel configuration                                  |

## 8. API Design (FastAPI)

**Konvensi:** prefix `/api/v1`; auth cookie sesi; tiap endpoint server cek izin user; paginasi `?page=&limit=`; error seragam `{error: {code, message}}`.

| Grup | Endpoint | Fungsi |
| --- | --- | --- |
| /auth | GET /auth/discord/login, GET /auth/discord/callback, POST /auth/logout, GET /auth/me | Login OAuth2, sesi |
| /users | GET /users/me, PUT /users/me/profile, DELETE /users/me/data | Profil, preferensi, hapus data |
| /servers | GET /servers, GET /servers/{id}, GET /servers/{id}/stats | Server yang dikelola, statistik |
| /settings | GET/PUT /servers/{id}/settings, GET/PUT /servers/{id}/commands/{name} | Konfigurasi, toggle command |
| /economy | GET .../economy/leaderboard, GET .../economy/users/{uid}, POST .../economy/users/{uid}/adjust, GET/POST/PUT/DELETE .../shop/items | Leaderboard, saldo, adjust (admin), CRUD shop |
| /moderation | GET .../moderation/logs, GET/DELETE .../warnings, GET/PUT .../automod | Log, warn, aturan automod |
| /ai | GET/DELETE .../ai/conversations/{cid}, GET/PUT .../ai/persona, GET/DELETE .../ai/memories | Riwayat, persona, memori |

Contoh `PUT /servers/{id}/settings`:

```
Request:  {log_channel_id: 123, welcome_channel_id: 456, features: {ai: true}}
Response: 200 {server_id: 1, log_channel_id: 123, ..., updated_at: ...}
Error:    403 {error: {code: forbidden, message: Butuh izin Manage Server}}
```

## 9. Security Planning

- **Environment variable:** rahasia hanya di `.env` (di-gitignore) via pydantic-settings; token dev dan prod dipisah; token yang pernah bocor langsung di-reset.
- **API key:** key AI dan token bot hanya di backend/bot, tidak di dashboard atau log; satu key per environment; rotasi berkala.
- **Discord OAuth:** parameter `state`, token exchange di server, cookie httpOnly + Secure + SameSite, sesi berumur pendek, scope minimal (identify, guilds).
- **Permission:** cek di dua tempat (bot dan API, cek ulang Manage Server tiap request); izin bot minimal; hormati hierarki role.
- **Database:** user DB hak minimal, akses lewat ORM, backup terjadwal, simpan seperlunya, hapus data atas permintaan user.
- **AI:** isi chat dianggap data tak tepercaya (prompt injection); tool dicek terhadap permission **user**, bukan AI; aksi destruktif butuh konfirmasi; `allowed_mentions=none`; user diberi tahu pesannya dikirim ke penyedia AI.
- **Abuse:** rate limit, cooldown, kuota AI harian, batas input/output; `pip-audit` di CI.

## 10. Deployment Planning

**Sekarang (laptop):** `docker-compose.yml` untuk PostgreSQL (atau Supabase gratis), bot/API/dashboard jalan manual, backup `pg_dump`.

**Nanti (VPS):**

```
VPS (Docker Compose): bot | api | postgres | redis | caddy (HTTPS + reverse proxy)
Vercel: dashboard React → https://api.domainmu (CORS dibatasi ke domain dashboard)
```

| CI/CD (GitHub Actions) | Pemicu | Isi |
| --- | --- | --- |
| CI | Pull request | ruff, mypy, pytest (service Postgres), build dashboard |
| Build | Merge ke main | Build image Docker, push ke GHCR |
| Deploy | Setelah build | SSH ke VPS: `docker compose pull && up -d`, lalu `alembic upgrade head` |
| Dashboard | Merge ke main | Vercel auto-deploy |

Tambahan: healthcheck, restart policy `unless-stopped`, backup database terjadwal.

## 11. Coding Standard

- **Clean Architecture:** dependensi mengalir `cogs / api → services → repositories → models`; service tidak boleh import `discord`.
- **OOP + DI:** service dan repository berupa class; dependensi disuntik lewat constructor atau `Depends` FastAPI.
- **Async penuh:** tanpa `requests` dan `time.sleep`; pakai `aiohttp`/`httpx` dan SQLAlchemy async.
- **Type hints** wajib; `mypy` strict untuk `services/` dan `ai/`.
- **Logging terstruktur** (JSON) dengan `guild_id`, `user_id`, `command`.
- **Error handling:** hierarki exception sendiri (`AkizaError` → `InsufficientFunds`, `PermissionDenied`, `QuotaExceeded`) dipetakan ke pesan Discord dan kode HTTP.
- **Transaksi:** satu unit of work per use case; saldo dan ledger ditulis bersamaan.

## 12. MVP, Advanced, dan Prioritas

**MVP (±1 bulan, tanpa dashboard):** fase 1-4: struktur baru, PostgreSQL + migrasi, `/setup`, AI chat (potong koin + kuota global), ekonomi dengan ledger, fun/utility inti, moderasi dasar + log. Dashboard dimulai setelah bot stabil.

**Advanced (production):** dashboard lengkap, memory + semantic search, automod penuh, Redis, multi-agent orchestrator, analytics, monitoring (Sentry/Prometheus), sharding, tier premium.

| Fitur                                        | Impact | Kesulitan | Urutan        |
| -------------------------------------------- | ------ | --------- | ------------- |
| Struktur modular + service layer, PostgreSQL | Tinggi | Sedang    | 1 (fondasi)   |
| AI chat + gating koin                        | Tinggi | Sedang    | 2             |
| Ledger ekonomi                               | Tinggi | Rendah    | 2             |
| Server settings + log, reminder              | Sedang | Rendah    | 3 (quick win) |
| Automod                                      | Sedang | Sedang    | 4             |
| Dashboard                                    | Tinggi | Tinggi    | 5             |
| Memory semantik, multi-agent                 | Sedang | Tinggi    | 6-7           |
| Music, calendar                              | Rendah | Tinggi    | Terakhir      |

## 13. AI Orchestrator Architecture

Orchestrator adalah pusat otak: memahami maksud user, memilih agent atau fungsi biasa, mengatur workflow, konteks, dan memory, serta menangani error dan fallback. Prinsip: pakai AI hanya bila perlu; selebihnya fungsi biasa yang murah dan deterministik.

```
User Discord → Discord Gateway → Bot (cog) → AI Orchestrator
        ┌────────────┬──────────────┬──────────────┬────────────────┐
     AI Agent   Economy Agent   Utility Agent   Moderation Agent
        └────────────┴──── Tools / Services / Database / API ────┘
```

**A. Intent Router.** Tiga tahap, dari yang paling murah: (1) slash/prefix command langsung ke handler tanpa AI; (2) aturan kata kunci/regex untuk intent umum; (3) klasifikasi LLM dengan output JSON `{intent, agent, confidence, args}` hanya bila tahap 1-2 gagal. Confidence rendah berarti tanya klarifikasi atau jatuh ke AI Agent. Bahasa natural hanya diproses bila bot di-mention atau di channel AI khusus (hemat kuota).

| Pesan                            | Agent                                |
| -------------------------------- | ------------------------------------ |
| berapa saldo saya?               | Economy Agent                        |
| ingatkan saya besok jam 8        | Utility Agent                        |
| jelaskan konsep machine learning | AI Agent                             |
| warn @user karena spam           | Moderation Agent (izin + konfirmasi) |

**B. Task Planner.** Aktif hanya untuk permintaan multi-langkah (ditandai router). Output rencana JSON `steps[{id, tool, args, depends_on}]`, maksimal 6 langkah, tiap langkah divalidasi (tool ada, user berhak). Langkah destruktif atau yang mengirim ke orang lain butuh konfirmasi tombol. Contoh: laporan server mingguan → (1) ambil data server → (2) analisis statistik → (3) generate laporan AI → (4) kirim ke admin.

**C. Agent Executor.** Interface `Agent.handle(ctx, intent) -> AgentResult`. Executor menjalankan langkah berurutan atau paralel (jika independen), retry sekali, lalu fallback atau laporan parsial. Agent tidak menyentuh database langsung, hanya lewat tool yang memanggil service.

**D. Memory System.**

| Jenis | Isi | Penyimpanan |
| --- | --- | --- |
| Short-term | Percakapan aktif + ringkasan bergulir | Memori/Redis (TTL) + tabel `messages` |
| Long-term terstruktur | Preferensi, kebiasaan, info yang diminta disimpan | PostgreSQL (`user_profiles`, `memories`) |
| Long-term semantik | Fakta/catatan dicari berdasarkan makna | pgvector di PostgreSQL yang sama |

Rekomendasi: pgvector dulu, bukan vector database terpisah (satu DB, satu backup, cukup untuk skala awal). Aturan tulis: simpan hanya yang dinyatakan eksplisit, deduplikasi, user bisa melihat dan menghapus. Retrieval: top-k berdasarkan kemiripan dan kebaruan.

**E. Context Management.** Context builder merakit prompt dengan batas token: persona global + override server; info server singkat; profil user + level permission; memory relevan (top-k); ringkasan lama + N pesan terakhir; daftar tool yang boleh dipakai user itu.

**F. Tool Calling.** Registry tool dengan JSON schema dan metadata `permission`, `side_effect` (read/write/destructive), `cost`, `timeout`. Alur: LLM meminta tool → validasi argumen (Pydantic) → cek permission **user** → jalankan → hasil kembali ke LLM (maksimal 3 putaran). Contoh: `get_balance` (read), `get_weather` (read, API eksternal), `create_reminder` (write), `get_server_stats` (read, admin), `warn_user` (destructive, wajib konfirmasi).

**G. Decision Flow.**

```
User Message → Message Analyzer (bersihkan, cek mention/channel)
  → Intent Detection (rule → LLM)
  → Context Retrieval (profile, memory, history, permission, tools)
  → Planning (hanya jika multi-step)
  → Tool / Agent Execution (retry + fallback)
  → Response Generation
  → Memory Update + potong koin (refund otomatis jika gagal)
```

**Error handling:** timeout provider → retry → provider cadangan → mode terbatas (fungsi non-AI); kuota habis → pesan jelas, koin tidak dipotong; tool gagal → dijelaskan ke user.

**H. Evaluasi Teknologi.**

| Opsi | Skalabilitas | Maintenance | Performa | Kompleksitas |
| --- | --- | --- | --- | --- |
| Custom Python orchestrator | Baik | Baik (kode sendiri, mudah debug) | Terbaik | Rendah-sedang |
| Native tool calling (API OpenAI-compatible) | Baik | Sangat baik | Baik | Rendah |
| LangChain | Baik | Sedang (abstraksi tebal, API sering berubah) | Sedang | Sedang-tinggi |
| LangGraph | Sangat baik untuk workflow stateful | Baik | Baik | Tinggi |

**Rekomendasi:** mulai dengan orchestrator Python tipis di atas native tool calling lewat interface `LLMProvider`. Sebagian besar request hanya satu langkah, jadi framework berat belum perlu dan provider gratis mudah ditukar. LangChain tidak dijadikan fondasi. LangGraph layak dipertimbangkan di Level 3 saat butuh workflow stateful multi-agent, checkpoint, dan human-in-the-loop. Ini penilaian umum; library cepat berubah, jadi cek dokumentasi terbaru sebelum memilih.

## 14. Future AI Assistant Capability

| Level | Kemampuan | Syarat naik level |
| --- | --- | --- |
| 1 | Chat AI, command, otomasi dasar | MVP stabil, kuota dan koin terkontrol |
| 2 | Memory, respons personal, otomasi tugas dari bahasa natural | Memory bisa dilihat/dihapus, intent router akurat |
| 3 | Multi-agent, workflow otonom terbatas, planning lanjutan | Tool registry matang, konfirmasi aksi, logging lengkap |
| 4 | Ekosistem asisten personal (lintas server, kalender/email, dashboard personal) | Infrastruktur produksi, privasi dan consent jelas |

```
Discord AI Assistant
├── Discord Bot Core
├── AI Orchestrator  ← pusat otak
├── Agents: AI | Economy | Utility | Moderation
├── Services: Database | Scheduler | API Integration
├── Memory System
├── FastAPI Backend
└── React Dashboard
```

## Risiko Utama

| Risiko                               | Mitigasi                                                |
| ------------------------------------ | ------------------------------------------------------- |
| Kuota AI gratis cepat habis          | Kuota global + koin + cooldown, multi-provider          |
| Scope terlalu besar untuk solo dev   | Ikuti MVP; dashboard setelah bot stabil                 |
| Abuse koin (akun alt)                | Batas transfer, batas `/ask` per hari, syarat usia akun |
| Privasi data percakapan              | Retensi terbatas, `/forget`, pemberitahuan ke user      |
| Free tier dan fitur provider berubah | Interface `LLMProvider`, tidak terikat satu vendor      |

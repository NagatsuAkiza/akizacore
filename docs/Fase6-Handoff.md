# AkizaCore - Claude Handoff

Dokumen ini menggantikan handoff sebelumnya (termasuk draft `Fase6-Handoff.md`). Terakhir diperbarui **13 Okt 2026**.

## Cara memakai handoff ini

Workspace: `d:\Project\AkizaCore` (Windows, PowerShell). Repo: `github.com/NagatsuAkiza/akizacore`, branch `main`.

**Posisi commit yang sudah pasti:** `a52cc5 feat(api): add FastAPI skeleton with uniform errors, health checks, and CORS` (sudah di `origin/main`, author pemilik).

**Task 6a-1 (skeleton API)** patch telah di kerjakan.

Sebelum mengubah kode:

1. Baca file ini.
2. Baca `docs/AkizaCore - Project Plan.md` (bagian 7 Dashboard, 8 API, 9 Security).
3. Baca file penting yang disebut di bawah.
4. Jalankan validasi baseline dan cocokkan angkanya.
5. Pertahankan arsitektur service/gateway yang ada. Jangan menyentuh Fase 6b (React) sebelum 6a stabil.

## Tujuan project

AkizaCore adalah Discord AI Assistant multifungsi berbasis Python: bot `discord.py`, service layer murni (tanpa `import discord`), SQLAlchemy async + Alembic + PostgreSQL, AI orchestrator dengan provider interface dan tool calling, serta backend API + dashboard web (Fase 6). Bot dan API berbagi `Services` yang sama.

Python minimum `>=3.12`. Quality gate: ruff, mypy (strict untuk `services/` dan `ai/`), pytest.

## Status roadmap

- **Fase 1-5: selesai (MVP).** Fondasi, database + user, AI assistant, economy, moderasi.
- **Fase 6 - Dashboard: sedang berjalan.** Dimulai 13 Okt 2026 atas instruksi pemilik.
  - **6a Backend API** (FastAPI, tanpa UI):
    - [x] 6a-1 Skeleton: app factory, format error seragam, health check, CORS, `ApiSettings` (patch `api-skeleton`)
    - [x] 6a-2 Login Discord OAuth2 + sesi: tabel `sessions` (migrasi `0007_user_sessions`), `AuthService`, endpoint `/auth/discord/login`, `/auth/discord/callback`, `/auth/logout`, `/auth/me`, cookie httpOnly, validasi state CSRF, `global_name` di `User` dan `UserInfo`, `Unauthorized` exception, 14 test baru
    - [ ] 6a-3 Daftar server yang dikelola user (Manage Server + bot aktif), izin dicek ulang tiap request
    - [ ] 6a-4 `GET/PUT /servers/{id}/settings` memakai `SettingsService`
    - [ ] 6a-5 Endpoint baca: stats, leaderboard, modlog, warnings (paginasi `?page=&limit=`)
    - [ ] 6a-6 Test API lintas-server (401/403, akses server lain)
  - [x] **6b Dashboard React**: scaffold Vite + React + TypeScript + Tailwind CSS v4 + React Router v7 + TanStack Query v5 selesai. Meliputi layout dashboard, auth guard, komponen navigasi, query hooks, serta halaman Login, Callback, Server list, Overview, Settings, Economy, dan Moderation.
  - **Ditunda:** adjust saldo dari web, CRUD shop dari web, editor persona dengan preview, riwayat percakapan AI, halaman memory, aksi destruktif moderasi lewat API (jangan diekspos pada Fase 6).

## Fitur yang sudah selesai

### Bot, owner, dan permission

- Owner dikonfigurasi lewat `OWNER_USER_ID`. Bypass hanya untuk batasan operasional (AI toggle/opt-out/cooldown/kuota/biaya, cooldown daily/work, batas umur akun dan limit harian transfer, cooldown XP chat, izin `/setup`, status admin AI tool). Validasi fundamental (input tidak valid, transfer ke diri sendiri, target safety moderasi) tetap berlaku. Ada test khusus di `tests/test_owner_bypass.py`.
- `/help`, prefix per server, `!help`.

### AI

- `/ask`, mention chat, `/translate`, persona per server, preferensi bahasa, history + `/forget` + retention cleanup, rule router, cooldown, kuota global/per-user, biaya koin dengan refund otomatis, tool calling (maks 3 putaran), reply context, explicit memory (CRUD, `services/memory.py`, migrasi `0006` dan `ea1b0647e76d`).

### Economy

- Ledger append-only, balance, daily, work, transfer (batas harian + umur akun), XP/level, `/leaderboard`, shop, inventory.

### Moderation

- Command manual (`/warn`, `/warnings`, `/clearwarns`, `/kick`, `/ban`, `/timeout`, `/untimeout`, `/purge`, `/modlog`, `/automod`) dan automod anti-spam/anti-link.
- AI moderation tools: `moderation_warn`, `moderation_warnings`, `moderation_clear_warnings`, `moderation_modlog`, `moderation_request`. `moderation_request` tidak langsung bertindak: hanya membuat pending request dan token untuk `/confirm`.
- **Confirmation flow yang sudah di-harden (commit `7f4dc28`):**
  - Izin Discord spesifik sama dengan command manual: kick -> `kick_members`, ban -> `ban_members`, timeout/untimeout -> `moderate_members`, purge -> `manage_messages` (di channel target), add/remove role -> `manage_roles`. Warn/warnings/modlog butuh `moderate_members`; clear warnings butuh `manage_guild`. Manage Server saja tidak cukup. Owner bot bypass izin, bukan target safety.
  - Token terikat guild + actor, kedaluwarsa 120 detik, sekali pakai; percobaan salah tidak menghabiskan token.
  - Semua parameter terikat lewat closure; prompt konfirmasi menampilkan target (nama + ID), alasan, durasi, jumlah, dan role.
  - Saat `/confirm`: izin pemohon dan hierarchy target/role divalidasi ulang dengan data member terbaru.
  - Role ditolak bila `@everyone`, dikelola bot/integrasi, atau sama/lebih tinggi dari role bot atau role tertinggi pemohon.
  - Kegagalan setelah konfirmasi dicatat ke moderation log sebagai `ai_<aksi>_failed`; sukses sebagai `ai_<aksi>`.
  - Registry menyembunyikan tool moderasi kecuali user admin, modul `moderation` aktif, dan gateway tersedia (`Tool.needs_moderation`).
- Fun MVP: `/joke`, `/meme`, `/react`, `/poll`.

### API (Fase 6, task 6a-1)

- `src/akizacore/api/app.py`: `create_app()` + `app` modul-level (`uvicorn akizacore.api.app:app --reload`). Engine lazy, `Services.build(...)` tanpa provider AI. Docs `/api/v1/docs` hanya saat `ENVIRONMENT=dev`; OpenAPI di `/api/v1/openapi.json`.
- `api/errors.py`: semua error berformat `{"error": {"code", "message"}}` (domain `AkizaError` memakai `http_status`; validasi 422 `validation_error`; HTTP 404/405 dst; error tak terduga 500 `internal_error` tanpa detail).
- `api/deps.py`: `ServicesDep`, `EngineDep`. `api/routers/health.py`: `GET /api/v1/health`, `GET /api/v1/health/ready`.
- `config.ApiSettings`: `environment`, `database_url`, `dashboard_origins` (JSON list, wildcard `*` ditolak karena memakai cookie).

## Keputusan terbuka (perlu pemilik)

**Strategi sesi untuk 6a-2.** Rekomendasi: **tabel sesi di database** (butuh migrasi baru).

- Alasan: izin Manage Server harus dicek ulang tiap request lewat `GET /users/@me/guilds`, sehingga access token OAuth harus disimpan di server. Tabel sesi memungkinkan logout/pencabutan yang efektif dan menyimpan token di sisi server (pertimbangkan enkripsi). Cookie hanya berisi ID sesi acak.
- Alternatif: cookie bertanda tangan (`itsdangerous`, stateless, tanpa migrasi), tetapi token Discord tidak bisa disimpan dengan aman dan sesi tidak bisa dicabut dari server.
- Cache daftar guild dengan TTL pendek per sesi untuk menghindari rate limit Discord.

Field konfigurasi baru yang diperlukan 6a-2 (usulan, tambahkan juga ke `.env.example`): `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_OAUTH_REDIRECT_URI`, `SESSION_TTL_S`, dan `DASHBOARD_URL` untuk redirect setelah login. OAuth: parameter `state`, tukar code di server (`httpx`), scope minimal `identify` + `guilds`, cookie `httpOnly` + `Secure` + `SameSite`, sesi berumur pendek.

## File penting

- `src/akizacore/services/container.py` - `Services.build(...)` (dipakai bot dan API)
- `src/akizacore/api/app.py`, `api/errors.py`, `api/deps.py`, `api/routers/health.py`
- `src/akizacore/config/settings.py` - `Settings`, `DatabaseSettings`, `ApiSettings`
- `src/akizacore/core/exceptions.py` - hierarki `AkizaError` (punya `user_message` dan `http_status`)
- `src/akizacore/cogs/ai/chat.py` - `_ConfirmationManager`, `_DiscordModerationGateway`, `/confirm`
- `src/akizacore/ai/tools/{base,builtin,registry,executor}.py` - kontrak tool, permission/feature/gateway filtering
- `src/akizacore/services/{economy,moderation,settings,stats,memory}.py`
- `src/akizacore/cogs/settings/setup.py` - validasi `/setup` yang harus setara dengan endpoint settings
- `tests/conftest.py` (fixture `session_factory`, database `akizacore_test`), `tests/test_api_core.py`, `tests/test_moderation_gateway.py`, `tests/test_owner_bypass.py`, `tests/test_confirmation.py`, `tests/test_tools.py`
- `docs/AkizaCore - Project Plan.md` - roadmap utama

## Validasi terakhir

Dijalankan di sandbox dengan PostgreSQL lokal (tanpa Postgres, test database ter-skip):

| Kondisi                       | pytest     |
| ----------------------------- | ---------- |
| `origin/main` di `7f4dc28`    | 240 passed |
| + patch `api-skeleton` (6a-1) | 261 passed |

Ruff check, ruff format check, dan mypy bersih pada keduanya. Ada satu warning dependency `audioop` dari `discord.player` (bukan failure).

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
```

Prasyarat: `docker compose up -d` (PostgreSQL) dan `pip install -e ".[dev,db,ai,api]"`.

## Batasan dan utang yang diketahui

- `moderation_clear_warnings` dan `moderation_warn` masih berjalan langsung tanpa `/confirm`. Karena reply context diteruskan ke AI, ini rawan prompt injection. Rekomendasi: pindahkan `clear_warnings` ke alur konfirmasi.
- Token konfirmasi hanya di memori proses (hilang saat restart) dan belum ada batas jumlah token tertunda per admin. Untuk production: Redis atau tabel database, plus fingerprint parameter.
- `/untimeout` manual tidak memanggil `_check_target` (tanpa cek hierarchy).
- `Services` di API memakai `EconomyConfig` default, bukan nilai `.env` bot (`EconomyConfig.from_settings` butuh `Settings` penuh dengan token Discord). Aman untuk endpoint baca; samakan sebelum ada endpoint yang mengubah saldo.
- Redis belum ada: cooldown, rate limit, dan cache masih in-memory (single process).
- Scheduler/worker untuk retention cleanup belum ada untuk deployment.
- `OWNER_USER_ID` punya default yang tertulis di `config/settings.py`; pindahkan ke `.env` saja bila repo dipublikasikan luas.
- Provider AI nyata dan end-to-end di Discord test server tetap perlu diuji dengan credential lokal.
- Nama file migrasi `ea1b0647e76d_...` berbeda gaya dari seri numerik (`0001`-`0006`); fungsinya benar (satu head).

## Aturan implementasi

- Dependensi mengalir `cogs / api -> services -> repositories -> models`. Router hanya validasi input, cek izin, dan memanggil service; jangan menduplikasi logika bisnis dan jangan query database dari router.
- Service tidak boleh import `discord`. API tidak memanggil bot lewat HTTP; ia memakai `Services` langsung.
- Authorization ditentukan backend dari data Discord/DB, bukan dari prompt, output model, atau input klien. `ToolContext.is_admin` ditentukan backend. Jangan percaya argumen `confirmed=True` dari LLM.
- Cek izin Manage Server di **setiap** request ber-`server_id`; jangan percaya ID dari path tanpa verifikasi.
- Gunakan `AkizaError` (dengan `http_status`) untuk error yang boleh tampil ke user. Detail internal hanya ke log.
- Async penuh, type hints wajib, rahasia hanya di `.env` dan tidak masuk log atau respons.
- Jaga backward compatibility Fase 1-5; jangan menghapus atau melemahkan test yang ada demi membuat test baru lolos.
- Tambahkan regression test sebelum menganggap perubahan selesai. Perubahan skema wajib lewat migrasi Alembic.
- Jangan menambah dependensi tanpa alasan; jalankan `pip-audit`.

### Alur kerja commit

Commit harus berasal dari pemilik, bukan dari Claude. Claude mengirim:

1. `<nama>.patch` - diff biasa (`git diff --cached --binary`), tanpa metadata author
2. `<nama>.msg.txt` - pesan commit (konvensional: `feat(api): ...`)
3. `apply-akiza-patch.ps1` - script yang dipakai ulang untuk semua patch

Pemilik menaruh ketiganya di luar folder repo (mis. `D:\Project`) dan menjalankan:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Project\apply-akiza-patch.ps1 -Patch D:\Project\<nama>.patch
```

Script menerapkan patch ke staging, memasang dependensi, menjalankan ruff + mypy + pytest, lalu commit memakai identitas git pemilik. Bila validasi gagal, perubahan dibatalkan otomatis. Satu sub-task = satu patch = satu commit. Setelah itu pemilik yang menjalankan `git push`.

## Instruksi singkat untuk Claude

1. Verifikasi `git log` (apakah 6a-1 sudah masuk) dan jalankan validasi baseline.
2. Minta keputusan strategi sesi (atau pakai rekomendasi tabel sesi bila pemilik setuju), lalu kerjakan **6a-2**: settings OAuth, migrasi tabel sesi, endpoint `/auth/discord/login`, `/auth/discord/callback`, `/auth/logout`, `/auth/me`, beserta test (state salah, code tidak valid dengan `httpx.MockTransport`, cookie flags, logout mencabut sesi).
3. Lanjut berurutan ke 6a-3 sampai 6a-6. Setelah 6a stabil, tanyakan pemilik sebelum memulai 6b.
4. Setelah setiap sub-task laporkan: file yang berubah, hasil validasi, risiko tersisa, dan apakah perlu migrasi.
5. Perbarui dokumen ini dan `docs/AkizaCore - Project Plan.md` di akhir setiap sub-task, bukan menunggu akhir sesi.

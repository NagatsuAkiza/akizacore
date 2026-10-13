# AkizaCore

AkizaCore adalah AI Discord Assistant multifungsi yang menggabungkan percakapan AI,
ekonomi komunitas, utility server, konfigurasi, dan moderasi dalam satu bot.

## Keunggulan

- **AI yang terkontrol** — `/ask` dan `/translate` menggunakan service layer dengan
  persona per server, pembatasan kuota, cooldown, biaya koin, dan retensi riwayat.
- **Privasi percakapan** — user dapat menghapus riwayatnya dengan `/forget`, sementara
  riwayat lama dibersihkan otomatis sesuai konfigurasi retensi.
- **Ekonomi berbasis ledger** — saldo, XP, level, hadiah harian, pekerjaan, transfer,
  leaderboard, toko, dan inventory dikelola melalui transaksi yang tercatat.
- **Moderasi terstruktur** — warning, eskalasi auto-timeout, kick, ban, timeout,
  purge, moderation log, dan automod anti-spam serta anti-link.
- **Konfigurasi per server** — admin dapat mengatur channel, autorole, fitur yang aktif,
  dan persona AI melalui command `/setup` serta `/persona`.
- **Owner control** — owner bot dapat melakukan operasi administratif yang diperlukan
  tanpa menghilangkan validasi keselamatan target moderasi.
- **Arsitektur mudah dikembangkan** — cog Discord tetap tipis; business logic dipisah
  ke service layer, repository, schema, dan migration database.
- **Bantuan yang selalu terbaru** — `/help` membaca command yang sedang terdaftar dan
  mengelompokkannya berdasarkan fitur.

## Command berdasarkan fitur

Gunakan `/help` di Discord untuk melihat daftar aktual dari bot. Command berikut
merupakan fitur yang tersedia saat ini.

### AI Assistant

- `/ask` — bertanya atau meminta bantuan kepada AI.
- `/translate` — menerjemahkan teks ke bahasa tujuan.
- `/forget` — menghapus riwayat percakapan AI milik sendiri di server.
- `/memory save` — menyimpan memory AI secara eksplisit untuk server ini.
- `/memory list` — melihat memory AI yang tersimpan di server ini.
- `/memory delete` dan `/memory clear` — menghapus satu atau seluruh memory AI
  milik sendiri di server ini.
- `/persona view|set|reset` — melihat atau mengatur gaya bicara AI server (admin).

Bot juga dapat merespons ketika di-mention langsung di channel.

Memory AI bersifat eksplisit: bot hanya menyimpan teks yang kamu masukkan melalui
`/memory save`. Memory terisolasi per server dan per user, sehingga tidak dibagikan
ke server lain atau member lain. `/forget` hanya menghapus riwayat percakapan; gunakan
`/memory delete` atau `/memory clear` untuk menghapus memory tersimpan. Jika fitur AI
dinonaktifkan untuk akunmu, `/memory save` dan penggunaan memory AI tidak tersedia.

### Economy

- `/balance` — melihat saldo, XP, dan level.
- `/daily` — mengambil hadiah harian.
- `/work` — bekerja untuk mendapatkan koin dengan cooldown.
- `/leaderboard` — melihat peringkat koin atau XP.
- `/transfer` — mengirim koin ke member lain dengan batas harian.
- `/shop` — melihat item yang tersedia.
- `/buy` — membeli item.
- `/inventory` — melihat item yang dimiliki.
- `/shopadmin add|remove` — mengelola item toko (admin/owner).

### Moderation

- `/warn`, `/warnings`, `/clearwarns` — mengelola warning member.
- `/kick`, `/ban`, `/timeout`, `/untimeout` — tindakan moderasi member.
- `/purge` — menghapus pesan terakhir dalam channel.
- `/modlog` — melihat aksi moderasi terbaru.
- `/automod` — melihat atau mengubah konfigurasi anti-spam dan anti-link.

### Fun

- `/joke` — mendapatkan lelucon singkat.
- `/meme` — membuat meme teks sederhana.
- `/react` — mengirim reaction emoji.
- `/poll` — membuat poll interaktif dengan tombol voting.

### AI moderation

AI dapat mengusulkan kick, ban, timeout/untimeout, purge, dan add/remove role melalui
`moderation_request`. Aksi destruktif tidak langsung dijalankan: admin yang membuat
permintaan harus menjalankan `/confirm` dengan token yang diberikan AI dalam 120 detik.
Token terikat pada server dan admin pembuatnya, serta hanya dapat digunakan sekali.

### Server Settings

- `/setup view` — melihat konfigurasi server.
- `/setup channels` — mengatur channel log, welcome, dan autorole.
- `/setup feature` — mengaktifkan atau menonaktifkan modul.
- `/setup prefix` — mengatur prefix command teks bot.

### Utility

- `/ping` — memeriksa latensi bot.
- `/userinfo` — melihat informasi member.
- `/serverinfo` — melihat statistik server.
- `/help` — melihat command berdasarkan fitur.

Prefix default adalah `!`. Admin dapat menggantinya melalui `/setup prefix`.
Saat ini prefix menyediakan command bantuan teks seperti `!help`; command utama
tetap menggunakan slash command agar parameter, izin, dan validasinya konsisten.

## Quick start (laptop / Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env      # isi DISCORD_TOKEN
python -m akizacore.main
```

## API dashboard (Fase 6)

```powershell
pip install -e ".[dev,db,ai,api]"
uvicorn akizacore.api.app:app --reload   # http://127.0.0.1:8000/api/v1/health
```

Dokumentasi interaktif (hanya `ENVIRONMENT=dev`): `/api/v1/docs`. Skema OpenAPI:
`/api/v1/openapi.json`. Semua error berformat `{"error": {"code": ..., "message": ...}}`.

## Perintah harian

```powershell
ruff check . ; ruff format .     # lint + format
mypy src                         # type check
pytest                           # test
```

## Arsitektur dan roadmap

Bot menggunakan arsitektur berlapis:

```text
Discord → Cog → Service → Repository → PostgreSQL
                 └──────→ AI provider / moderation rules
```

Arsitektur lengkap dan roadmap Fase 1–6 tersedia di
`docs/AkizaCore — Project Plan.md`.
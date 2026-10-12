# AkizaCore

AI Discord Assistant multifungsi: modul AI, ekonomi, hiburan, utility, moderasi, dan konfigurasi.

## Quick start (laptop / Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env      # isi DISCORD_TOKEN
python -m akizacore.main
```

## Perintah harian

```powershell
ruff check . ; ruff format .     # lint + format
mypy src                         # type check
pytest                           # test
```

Arsitektur dan roadmap: lihat `docs/AkizaCore — Project Plan.md`.
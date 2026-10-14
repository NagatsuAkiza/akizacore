"""AkizaCore Unified Development Runner

Menjalankan Bot Discord, FastAPI Backend (Uvicorn), dan React Dashboard (Vite)
secara bersamaan dalam satu terminal. Cukup tekan Ctrl + C untuk mematikan semua proses dengan bersih.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Enable ANSI escape sequences on Windows console
if sys.platform == "win32":
    os.system("")

ROOT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT_DIR / "dashboard"

# ANSI color codes
CYAN = "\033[36m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"

processes: list[tuple[str, subprocess.Popen[str]]] = []
shutdown_lock = threading.Lock()
is_shutting_down = False


def kill_proc_tree(pid: int) -> None:
    """Bunuh proses dan seluruh child processes (pohon proses)."""
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    else:
        with contextlib.suppress(Exception):
            os.killpg(os.getpgid(pid), 15)


def stop_all_processes() -> None:
    """Hentikan semua proses secara bersih."""
    global is_shutting_down
    with shutdown_lock:
        if is_shutting_down:
            return
        is_shutting_down = True

    print(f"\n{YELLOW}{BOLD}[DEV RUNNER] Menghentikan semua service...{RESET}", flush=True)
    for name, proc in processes:
        if proc.poll() is None:
            print(f"{YELLOW}[DEV RUNNER] Mematikan {name} (PID {proc.pid})...{RESET}", flush=True)
            kill_proc_tree(proc.pid)

    time.sleep(0.5)
    print(
        f"{GREEN}{BOLD}[DEV RUNNER] Semua service telah berhenti dengan bersih.{RESET}\n",
        flush=True,
    )


def stream_logs(name: str, color: str, proc: subprocess.Popen[str]) -> None:
    """Baca dan tampilkan stdout/stderr dengan prefix berwarna."""
    prefix = f"{color}[{name.upper():<9}]{RESET}"
    if proc.stdout is None:
        return
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            print(f"{prefix} {line.rstrip()}", flush=True)
    except Exception:
        pass


def get_python_executable() -> str:
    """Ambil python executable dari virtualenv bila tersedia."""
    if sys.platform == "win32":
        venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT_DIR / ".venv" / "bin" / "python"

    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def get_dashboard_runner() -> list[str]:
    """Cari runner paket untuk dashboard (bun diprioritaskan, fallback npm)."""
    if shutil.which("bun"):
        return ["bun", "run", "dev"]
    if shutil.which("npm"):
        return ["npm", "run", "dev"]
    return ["npx", "vite"]


def main() -> None:
    parser = argparse.ArgumentParser(description="AkizaCore Unified Development Runner")
    parser.add_argument("--no-bot", action="store_true", help="Jangan jalankan Bot Discord")
    parser.add_argument("--no-api", action="store_true", help="Jangan jalankan Backend API")
    parser.add_argument(
        "--no-dashboard", action="store_true", help="Jangan jalankan React Dashboard"
    )
    parser.add_argument("--api-only", action="store_true", help="Hanya jalankan Backend API")
    parser.add_argument("--bot-only", action="store_true", help="Hanya jalankan Bot Discord")
    parser.add_argument(
        "--dashboard-only", action="store_true", help="Hanya jalankan React Dashboard"
    )
    parser.add_argument(
        "--api-port", type=int, default=8000, help="Port untuk FastAPI (default: 8000)"
    )

    args = parser.parse_args()

    # Evaluasi service yang akan dijalankan
    run_bot = not args.no_bot
    run_api = not args.no_api
    run_dashboard = not args.no_dashboard

    if args.api_only:
        run_bot = False
        run_api = True
        run_dashboard = False
    elif args.bot_only:
        run_bot = True
        run_api = False
        run_dashboard = False
    elif args.dashboard_only:
        run_bot = False
        run_api = False
        run_dashboard = True

    py_exe = get_python_executable()

    print(f"{BOLD}===================================================={RESET}")
    print(f"{BOLD}       AkizaCore Unified Development Runner        {RESET}")
    print(f"{BOLD}===================================================={RESET}")
    print(f" Python  : {py_exe}")
    print(
        f" Services: "
        f"{'Bot [ON] ' if run_bot else 'Bot [OFF] '}"
        f"{'API [ON] ' if run_api else 'API [OFF] '}"
        f"{'Dashboard [ON]' if run_dashboard else 'Dashboard [OFF]'}"
    )
    print(
        f"{YELLOW} Tekan {BOLD}Ctrl + C{RESET}{YELLOW} kapan saja untuk mematikan semua service.{RESET}\n"
    )

    # 1. Start Backend API
    if run_api:
        api_cmd = [
            py_exe,
            "-m",
            "uvicorn",
            "akizacore.api.app:app",
            "--reload",
            "--port",
            str(args.api_port),
        ]
        api_proc = subprocess.Popen(
            api_cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        processes.append(("api", api_proc))
        threading.Thread(target=stream_logs, args=("api", GREEN, api_proc), daemon=True).start()

    # 2. Start Bot Discord
    if run_bot:
        bot_cmd = [py_exe, "-m", "akizacore.main"]
        bot_proc = subprocess.Popen(
            bot_cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        processes.append(("bot", bot_proc))
        threading.Thread(target=stream_logs, args=("bot", CYAN, bot_proc), daemon=True).start()

    # 3. Start React Dashboard
    if run_dashboard:
        dash_cmd = get_dashboard_runner()
        dash_proc = subprocess.Popen(
            dash_cmd,
            cwd=str(DASHBOARD_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=sys.platform == "win32",
            env=os.environ.copy(),
        )
        processes.append(("dashboard", dash_proc))
        threading.Thread(
            target=stream_logs, args=("dashboard", MAGENTA, dash_proc), daemon=True
        ).start()

    if not processes:
        print(f"{RED}Tidak ada service yang dipilih untuk dijalankan.{RESET}")
        return

    # Loop tunggu hingga salah satu keluar atau Ctrl+C
    try:
        while True:
            time.sleep(0.5)
            # Cek apakah ada service yang mati tak terduga
            for name, proc in processes:
                code = proc.poll()
                if code is not None and not is_shutting_down:
                    print(
                        f"\n{RED}{BOLD}[DEV RUNNER] Service '{name}' berhenti dengan exit code {code}.{RESET}",
                        flush=True,
                    )
                    stop_all_processes()
                    sys.exit(code if code != 0 else 1)
    except KeyboardInterrupt:
        stop_all_processes()
    except Exception as e:
        print(f"\n{RED}[DEV RUNNER] Error: {e}{RESET}", flush=True)
        stop_all_processes()


if __name__ == "__main__":
    main()

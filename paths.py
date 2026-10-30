# paths.py
import os, sys
from pathlib import Path

APP_NAME = "SecretManager"

def user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d

def db_path() -> Path:
    return user_data_dir() / "secrets.db"

def key_path() -> Path:
    return user_data_dir() / ".master_key"

def resource_dir() -> Path:
    """
    Folder that contains read-only assets bundled with the exe
    (scripts, icons...). For --onefile it is _MEIPASS,
    for --onedir it is sys._MEIPASS too (PyInstaller sets it both ways).
    Falls back to the script's folder when running from source.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent
def legacy_candidates() -> list[Path]:
    """
    Places where an old secrets.db / .master_key might live from a pre-update run.
    Checked in order; the first one that contains the file wins.
    """
    here = Path.cwd()
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    cands = [here]
    if exe_dir and exe_dir not in cands:
        cands.append(exe_dir)
    return cands    
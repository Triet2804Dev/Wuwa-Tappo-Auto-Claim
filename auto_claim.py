"""Wuwa Tappo Auto Claim
Author: github.com/Triet2804Dev
Fully automated chest opening with smart click balance maintenance.

Features:
- Automatic Token extraction: reads from config.json, decrypts from WebView2 Cookies or RAM.
- Resource saving: sends requests only when opening chests, 0 network requests during waiting.
- Discord Webhook notifications with item thumbnails and reward details.
- Intuitive and professional terminal dashboard with ANSI color support.
"""

import asyncio
import atexit
import base64
import ctypes
import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import winreg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw
import psutil
import pystray
import requests

# ----------------- CONSTANTS & PATHS -----------------
PROJECT_NAME = "Wuwa Tappo Auto Claim"
PROJECT_AUTHOR = "github.com/Triet2804Dev"
APP_VERSION = "1.0.1"
GITHUB_RELEASES_URL = "https://api.github.com/repos/Triet2804Dev/Wuwa-Tappo-Auto-Claim/releases/latest"
latest_version_info = None


def parse_version(v_str: str) -> tuple:
    """Convert version string 'v1.1.0' into a numeric tuple (1, 1, 0) for exact comparison."""
    try:
        nums = re.findall(r"\d+", str(v_str))
        return tuple(map(int, nums)) if nums else (0,)
    except Exception:
        return (0,)


def check_for_updates():
    """Check for new releases from GitHub Releases asynchronously on a background thread."""
    global latest_version_info, tray_icon
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "WuwaTappoAutoClaim",
        }
        resp = requests.get(GITHUB_RELEASES_URL, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            remote_tag = data.get("tag_name", "")
            remote_ver = remote_tag.lstrip("vV")
            if parse_version(remote_ver) > parse_version(APP_VERSION):
                latest_version_info = {
                    "version": remote_ver,
                    "download_url": data.get("html_url", "https://github.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim/releases"),
                }
                logger.info(f"Update available: v{remote_ver} (Current: v{APP_VERSION})")
                if tray_icon:
                    try:
                        tray_icon.notify(
                            f"A new version v{remote_ver} is available!\nVisit GitHub to update.",
                            "Wuwa Tappo Auto Claim",
                        )
                    except Exception:
                        pass
                if global_update_view_fn:
                    global_update_view_fn()
    except Exception as e:
        logger.debug(f"Update check skipped: {e}")


def delayed_update_check():
    """Wait 5 minutes (300 seconds) after startup before checking and notifying updates."""
    for _ in range(300):
        if not running_flag:
            return
        time.sleep(1)
    if running_flag:
        check_for_updates()

if getattr(sys, "frozen", False):
    WORKSPACE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", WORKSPACE_DIR)
else:
    WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = WORKSPACE_DIR

CONFIG_FILE = os.path.join(WORKSPACE_DIR, "config.json")
LOG_FILE = os.path.join(WORKSPACE_DIR, "auto_claim.log")

CHEST_COST = 1000            # Clicks consumed per chest
CLICK_GAIN_PER_CHEST = 1000  # Clicks automatically replenished per chest
MIN_BALANCE_MAINTAIN = 5000  # Safe minimum click balance threshold

SERVICE_BASE = "https://api-wutheringwaves-wuwatappo.kurogames-global.com"

# ----------------- AUTO-START & SYSTEM TRAY -----------------
TASK_NAME = "WuwaTappoAutoClaim"
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None
user32 = ctypes.windll.user32 if os.name == "nt" else None
console_hwnd = None
tray_icon = None
is_window_visible = True
running_flag = True
global_update_view_fn = None

# ----------------- LOGGING SETUP (FILE) -----------------
# Technical details are logged into auto_claim.log to keep the console UI clean.
logger = logging.getLogger("AutoClaim")
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# ----------------- TERMINAL UI & COLORS -----------------
class Color:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"

    # Reward rarity colors
    RARITY = {
        "epic": "\033[1;95m",     # Epic Purple
        "rare": "\033[1;94m",     # Rare Blue
        "uncommon": "\033[1;92m", # Uncommon Green
        "common": "\033[1;93m",   # Common Yellow
    }


def init_terminal():
    """Enable ANSI Escape Code support on Windows Terminal / cmd.exe."""
    global console_hwnd
    if os.name == "nt":
        try:
            h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(h_stdout, mode.value | 0x0004)
            kernel32.SetConsoleTitleW(f"{PROJECT_NAME} - {PROJECT_AUTHOR}")
            sys.stdout.write("\033[?25l")  # Hide blinking cursor for GUI-like clean output
            sys.stdout.flush()
            console_hwnd = kernel32.GetConsoleWindow()
            if console_hwnd:
                try:
                    hmenu = user32.GetSystemMenu(console_hwnd, False)
                    if hmenu:
                        user32.DeleteMenu(hmenu, 0xF060, 0x00000000)
                except Exception:
                    pass
        except Exception:
            pass


ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(s: str) -> int:
    """Calculate visible string length after stripping ANSI color codes."""
    return len(ANSI_REGEX.sub("", s))


BOX_WIDTH = 70


def make_top(title: str) -> str:
    dash_count = max(0, BOX_WIDTH - 6 - visible_len(title))
    return f"  ┌── {title} " + "─" * dash_count + "┐"


def make_mid(title: str) -> str:
    dash_count = max(0, BOX_WIDTH - 6 - visible_len(title))
    return f"  ├── {title} " + "─" * dash_count + "┤"


def make_bot() -> str:
    return "  └" + "─" * (BOX_WIDTH - 2) + "┘"


def box_line(content: str) -> str:
    """Format a line inside the border box with exact padding."""
    pad = max(0, BOX_WIDTH - 4 - visible_len(content))
    return f"  │  {content}{' ' * pad}│"


def render_banner():
    """Print the startup application banner."""
    w = BOX_WIDTH
    c = Color
    title_text = PROJECT_NAME.upper()
    author_text = PROJECT_AUTHOR
    print(f"\n{c.CYAN}  ╔{'═' * (w - 2)}╗{c.RESET}")
    print(f"{c.CYAN}  ║{c.BOLD}{c.YELLOW}{title_text.center(w - 2)}{c.RESET}{c.CYAN}║{c.RESET}")
    print(f"{c.CYAN}  ║{c.GRAY}{author_text.center(w - 2)}{c.RESET}{c.CYAN}║{c.RESET}")
    print(f"{c.CYAN}  ╚{'═' * (w - 2)}╝{c.RESET}\n")


# ----------------- TOKEN AUTO-DECRYPTION FROM COOKIES -----------------
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def get_token_from_cookies():
    """Automatically decrypt kuro_infoToken from WebView2 Cookies storage (works even when app is closed).
    Applies Chromium v24+ standard: validates and strips 32-byte SHA256(host) prefix.
    """
    local_state_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), r"com.kuro.wuwatappo.global\EBWebView\Local State"
    )
    cookies_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), r"com.kuro.wuwatappo.global\EBWebView\Default\Network\Cookies"
    )

    if not (os.path.exists(local_state_path) and os.path.exists(cookies_path)):
        return None

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]

        blob_in = DATA_BLOB(
            len(encrypted_key),
            ctypes.cast(ctypes.create_string_buffer(encrypted_key), ctypes.POINTER(ctypes.c_byte)),
        )
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            return None
        master_key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

        temp_cookies = os.path.join(os.environ.get("TEMP", ""), f"wuwatappo_ck_{uuid.uuid4().hex[:8]}.db")
        try:
            shutil.copy2(cookies_path, temp_cookies)
        except Exception:
            return None

        conn = sqlite3.connect(temp_cookies)
        cur = conn.cursor()

        # 1. Read Chromium Cookie database schema version
        version_row = cur.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        version = int(version_row[0]) if version_row else 0

        rows = cur.execute(
            "SELECT host_key, value, encrypted_value FROM cookies WHERE name = 'kuro_infoToken'"
        ).fetchall()
        conn.close()
        try:
            os.remove(temp_cookies)
        except Exception:
            pass

        for host, plain, enc_val in rows:
            if plain:
                return plain
            if enc_val and enc_val[:3] in (b"v10", b"v11"):
                iv = enc_val[3:15]
                ciphertext = enc_val[15:]
                aesgcm = AESGCM(master_key)
                decrypted = aesgcm.decrypt(iv, ciphertext, None)

                # Standard Chromium v24+: first 32 bytes is SHA256 of host
                if version >= 24:
                    expected_prefix = hashlib.sha256(host.encode("utf-8")).digest()
                    if decrypted[:32] == expected_prefix:
                        decrypted = decrypted[32:]

                token = decrypted.decode("utf-8", errors="ignore").strip()
                if re.fullmatch(r"[a-f0-9]{64}", token):
                    return token

                # Fallback check for 64-character hex if bound to another host
                m = re.search(rb"([a-f0-9]{64})", decrypted)
                if m:
                    return m.group(1).decode("utf-8")
    except Exception as e:
        logger.debug(f"Could not read token from cookies: {e}")
    return None


# ----------------- TOKEN EXTRACTION FROM RAM -----------------
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
kernel32 = ctypes.windll.kernel32


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("PartitionId", ctypes.c_ushort),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


def auto_detect_token_from_memory():
    """Scan and extract token from process memory if Wuwa Tappo is running."""
    tappo_pids = []
    my_pid = os.getpid()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            name = (p.info["name"] or "").lower()
            if name == "wuwatappo.exe":
                tappo_pids.append(p.info["pid"])
            elif name == "msedgewebview2.exe":
                try:
                    cmd = " ".join(p.cmdline() or []).lower()
                    if "wuwatappo" in cmd:
                        tappo_pids.append(p.info["pid"])
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    patterns = [
        re.compile(rb"kuro_infoToken=([a-f0-9]{64})"),
        re.compile(rb"kuro_infoToken[\"':\s=]+([a-f0-9]{64})"),
    ]
    for pid in tappo_pids:
        h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h:
            continue
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION()
        while kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            if mbi.State == 0x1000 and (mbi.Protect & 0xEE) and not (mbi.Protect & 0x100):
                buf = (ctypes.c_char * mbi.RegionSize)()
                nread = ctypes.c_size_t()
                if kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, mbi.RegionSize, ctypes.byref(nread)):
                    data = bytes(buf)[: nread.value]
                    for pat in patterns:
                        m = pat.search(data)
                        if m:
                            kernel32.CloseHandle(h)
                            return m.group(1).decode("utf-8")
            addr += mbi.RegionSize
        kernel32.CloseHandle(h)
    return None


def auto_detect_cid():
    """Automatically retrieve X-BLM-CID from LocalStorage LevelDB."""
    appdata = os.environ.get("LOCALAPPDATA", "")
    path = os.path.join(appdata, r"com.kuro.wuwatappo.global\EBWebView\Default\Local Storage\leveldb")
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.endswith(".ldb") or f.endswith(".log"):
                try:
                    with open(os.path.join(path, f), "rb") as fp:
                        d = fp.read()
                        m = re.search(rb"KURO_YCK_REQ_CID[\s\S]{1,20}?([a-f0-9]{32})", d)
                        if m:
                            return m.group(1).decode("utf-8")
                except Exception:
                    pass
    return None


# ----------------- SYSTEM TRAY & TASK SCHEDULER -----------------
def create_tray_icon_image():
    """Create or load 64x64 pixel icon for System Tray.
    Prefers loading from Hsin-Icon.png / Hsin-Icon.ico if present.
    """
    candidates = [
        os.path.join(WORKSPACE_DIR, "Hsin-Icon.png"),
        os.path.join(BUNDLE_DIR, "Hsin-Icon.png"),
        os.path.join(WORKSPACE_DIR, "Hsin-Icon.ico"),
        os.path.join(BUNDLE_DIR, "Hsin-Icon.ico"),
    ]
    for icon_path in candidates:
        if os.path.exists(icon_path):
            try:
                img = Image.open(icon_path).convert("RGBA")
                return img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.debug(f"Could not load icon {icon_path}: {e}")

    # Fallback default icon (vector treasure chest)
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(18, 140, 126), outline=(255, 215, 0), width=3)
    d.rectangle((16, 26, 48, 48), fill=(243, 156, 18), outline=(255, 255, 255), width=2)
    d.rectangle((14, 20, 50, 26), fill=(230, 126, 34), outline=(255, 255, 255), width=2)
    d.rectangle((29, 28, 35, 36), fill=(255, 215, 0), outline=(0, 0, 0), width=1)
    return img


def dpapi_encrypt(plain_text: str) -> str:
    """Encrypt plain string using Windows DPAPI (CryptProtectData).
    Only the current Windows user account on this machine can decrypt it.
    """
    if os.name != "nt" or not plain_text or plain_text.startswith("dpapi:"):
        return plain_text
    try:
        data = plain_text.encode("utf-8")
        blob_in = DATA_BLOB(
            len(data),
            ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)),
        )
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "WuwaToken", None, None, None, 0, ctypes.byref(blob_out)
        ):
            enc_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return "dpapi:" + base64.b64encode(enc_bytes).decode("ascii")
    except Exception as e:
        logger.debug(f"DPAPI encryption failed: {e}")
    return plain_text


def dpapi_decrypt(cipher_str: str) -> str:
    """Decrypt DPAPI token string using CryptUnprotectData."""
    if os.name != "nt" or not cipher_str or not cipher_str.startswith("dpapi:"):
        return cipher_str
    try:
        raw_b64 = cipher_str[6:].strip()
        cipher_bytes = base64.b64decode(raw_b64)
        blob_in = DATA_BLOB(
            len(cipher_bytes),
            ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_byte)),
        )
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            plain = ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return plain
    except Exception as e:
        logger.debug(f"DPAPI decryption failed: {e}")
    return cipher_str


def is_autostart_enabled() -> bool:
    """Check if Windows Task Scheduler autostart entry exists."""
    if os.name != "nt":
        return False
    try:
        res = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        return res.returncode == 0
    except Exception:
        return False


def set_autostart(enable: bool) -> bool:
    """Create or delete Windows Task Scheduler entry with highest privileges (/rl highest)."""
    if os.name != "nt":
        return False
    if enable:
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}"'
        else:
            script = os.path.abspath(__file__)
            py_exe = sys.executable
            cmd = f'"{py_exe}" "{script}"'
        try:
            res = subprocess.run(
                [
                    "schtasks", "/create",
                    "/tn", TASK_NAME,
                    "/tr", cmd,
                    "/sc", "onlogon",
                    "/rl", "highest",
                    "/f",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=0x08000000,
            )
            return res.returncode == 0
        except Exception:
            return False
    else:
        try:
            res = subprocess.run(
                ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=0x08000000,
            )
            return res.returncode == 0
        except Exception:
            return False


def save_config_key(key: str, val):
    """Update setting value in config.json."""
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    if key == "token" and isinstance(val, str) and not val.startswith("dpapi:"):
        val = dpapi_encrypt(val)
    cfg[key] = val
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Failed to save config key {key}: {e}")


def disable_console_close_button():
    """Disable Console window [X] Close button to prevent accidental closure.
    User can minimize to System Tray with [-] or right-click tray icon to exit.
    """
    global console_hwnd
    if os.name == "nt":
        if not console_hwnd:
            console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            try:
                hmenu = user32.GetSystemMenu(console_hwnd, False)
                if hmenu:
                    # SC_CLOSE = 0xF060, MF_BYCOMMAND = 0x00000000
                    user32.DeleteMenu(hmenu, 0xF060, 0x00000000)
            except Exception:
                pass


def hide_window(notify_user: bool = True):
    """Hide Console window to System Tray."""
    global is_window_visible, console_hwnd
    if os.name != "nt":
        return
    if not console_hwnd:
        console_hwnd = kernel32.GetConsoleWindow()
    if console_hwnd:
        user32.ShowWindow(console_hwnd, 0)  # SW_HIDE
    is_window_visible = False
    save_config_key("show_window", False)

    if tray_icon:
        try:
            tray_icon.update_menu()
        except Exception:
            pass

    if notify_user and tray_icon:
        try:
            tray_icon.notify(
                "Wuwa Tappo Auto Claim is running in the System Tray.\nRight-click tray icon to restore or exit.",
                "Wuwa Tappo Auto Claim",
            )
        except Exception:
            pass


def show_window(icon=None, item=None):
    """Restore Console window from System Tray."""
    global is_window_visible, console_hwnd
    if os.name != "nt":
        return
    if not console_hwnd:
        console_hwnd = kernel32.GetConsoleWindow()
    if console_hwnd:
        user32.ShowWindow(console_hwnd, 9)  # SW_RESTORE
        user32.ShowWindow(console_hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(console_hwnd)
        disable_console_close_button()

    is_window_visible = True
    save_config_key("show_window", True)

    if tray_icon:
        try:
            tray_icon.update_menu()
        except Exception:
            pass

    if global_update_view_fn:
        global_update_view_fn(in_place=False)


def toggle_window(icon=None, item=None):
    """Toggle Console window visibility."""
    global is_window_visible
    if is_window_visible:
        hide_window(notify_user=True)
    else:
        show_window()


def toggle_autostart(icon=None, item=None):
    """Toggle autostart with Windows via Task Scheduler."""
    current = is_autostart_enabled()
    new_state = not current
    success = set_autostart(new_state)
    if success:
        save_config_key("start_with_windows", new_state)
        msg = "Start with Windows enabled (Task Scheduler Admin)." if new_state else "Start with Windows disabled."
        if tray_icon:
            try:
                tray_icon.update_menu()
                tray_icon.notify(msg, "Wuwa Tappo Auto Claim")
            except Exception:
                pass


def exit_from_tray(icon=None, item=None):
    """Gracefully terminate application from System Tray."""
    global running_flag
    running_flag = False
    cleanup_pet_sync()
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
    os._exit(0)


def init_tray():
    """Start System Tray Icon in a background daemon thread."""
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "Hide Window" if is_window_visible else "Show Window",
            toggle_window,
            default=True,
        ),
        pystray.MenuItem(
            "Start with Windows",
            toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.MenuItem("Exit", exit_from_tray),
    )
    tray_icon = pystray.Icon(
        "WuwaTappoAutoClaim",
        create_tray_icon_image(),
        "Wuwa Tappo Auto Claim",
        menu,
    )
    t = threading.Thread(target=tray_icon.run, daemon=True)
    t.start()


def window_monitor_loop():
    """Monitor window minimize [-] event and hide to System Tray."""
    global console_hwnd, is_window_visible
    if os.name != "nt":
        return
    while running_flag:
        time.sleep(0.3)
        if not console_hwnd:
            console_hwnd = kernel32.GetConsoleWindow()
            if console_hwnd:
                disable_console_close_button()
        if console_hwnd and is_window_visible:
            try:
                if user32.IsIconic(console_hwnd):
                    hide_window(notify_user=True)
            except Exception:
                pass


def load_config():
    """Load configuration: read from config.json first, fallback to RAM / Cookies detection."""
    c = Color
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    cid = cfg.get("cid")
    raw_token = cfg.get("token")
    token = dpapi_decrypt(raw_token) if raw_token else None
    token_src = "config.json"

    # 1. Read token from config.json first
    if not token:
        # 2. If app is active: scan RAM
        token = auto_detect_token_from_memory()
        if token:
            token_src = "RAM Memory"
        else:
            # 3. Scan Cookies database
            token = get_token_from_cookies()
            if token:
                token_src = "WebView2 Cookies"

    # CID: Use machine CID if found, otherwise generate random UUID
    detected_cid = auto_detect_cid()
    cid_src = "Machine Storage"
    if detected_cid:
        cid = detected_cid
    elif not cid:
        cid = uuid.uuid4().hex
        cid_src = "Generated"
    else:
        cid_src = "config.json"

    if token:
        print(f"  {c.GREEN}[+] Token{c.RESET}      : {c.WHITE}{token[:8]}...{token[-8:]}{c.RESET} {c.GRAY}(From {token_src}){c.RESET}")
        logger.info(f"Loaded Token from {token_src}: {token[:8]}...{token[-8:]}")
    else:
        print(f"  {c.YELLOW}[!] Token not found automatically.{c.RESET}")
        raw_token = input("  >> Enter Bearer Token: ").strip().strip("'\"")
        if raw_token.lower().startswith("bearer "):
            raw_token = raw_token[7:].strip()
        token = raw_token
        token_src = "User Input"

    print(f"  {c.GREEN}[+] Device CID{c.RESET} : {c.WHITE}{cid[:6]}...{cid[-6:]}{c.RESET} {c.GRAY}({cid_src}){c.RESET}")
    logger.info(f"Using CID ({cid_src}): {cid}")

    webhook_url = cfg.get("discord_webhook", "").strip()
    if webhook_url:
        print(f"  {c.GREEN}[+] Discord Webhook{c.RESET}: {c.GREEN}Connected{c.RESET}")
    else:
        print(f"  {c.GRAY}[-] Discord Webhook: Disabled (Add 'discord_webhook' in config.json){c.RESET}")

    show_window = cfg.get("show_window", True)
    start_with_windows = cfg.get("start_with_windows", False)

    # Synchronize Task Scheduler status with config.json
    if start_with_windows and not is_autostart_enabled():
        set_autostart(True)
    elif not start_with_windows and is_autostart_enabled():
        set_autostart(False)

    cfg["token"] = dpapi_encrypt(token) if token else ""
    cfg["cid"] = cid
    if "discord_webhook" not in cfg:
        cfg["discord_webhook"] = ""
    cfg["show_window"] = show_window
    cfg["start_with_windows"] = start_with_windows

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    return token, cid, webhook_url, token_src, cid_src, show_window


# ----------------- DISCORD WEBHOOK NOTIFICATIONS -----------------
def get_asset_url(asset_name: str) -> str:
    """Generate image thumbnail URL for reward items."""
    base = "https://wutheringwaves-wuwatappo.kurogames-global.com"
    if not asset_name:
        return ""
    name_lower = asset_name.lower()
    if name_lower.startswith("accessory"):
        return f"{base}/accessory/{asset_name}"
    elif name_lower.startswith("role"):
        return f"{base}/character/{asset_name}"
    elif name_lower.startswith("emote"):
        return f"{base}/emote/{asset_name}"
    return f"{base}/{asset_name}"


def send_discord_webhook(
    webhook_url: str,
    nickname: str,
    place: str,
    asset_name: str,
    rarity: str,
    balance: int,
    left_wait_sec: int,
    right_wait_sec: int,
):
    """Send formatted chest claim notification embed to Discord Webhook."""
    if not webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return

    rarity_lower = rarity.lower() if rarity else "common"
    color_map = {
        "epic": 0x9B59B6,      # Purple Epic
        "rare": 0x3498DB,      # Blue Rare
        "uncommon": 0x2ECC71,  # Green Uncommon
        "common": 0xF1C40F,    # Yellow Common
    }
    embed_color = color_map.get(rarity_lower, 0x5865F2)
    image_url = get_asset_url(asset_name)
    place_label = "Left Chest" if place == "left" else "Right Chest"

    embed = {
        "title": f"🎁 {place_label} Claimed Successfully!",
        "color": embed_color,
        "fields": [
            {"name": "👤 Player", "value": nickname, "inline": True},
            {"name": "📦 Chest", "value": place_label, "inline": True},
            {"name": "💎 Rarity", "value": rarity.capitalize() if rarity else "Common", "inline": True},
            {"name": "✨ Reward Item", "value": f"`{asset_name}`", "inline": True},
            {"name": "🔘 Balance", "value": f"{balance:,} clicks", "inline": True},
            {
                "name": "⏳ Next Cooldowns",
                "value": f"Left: `{format_duration(left_wait_sec)}` | Right: `{format_duration(right_wait_sec)}`",
                "inline": False,
            },
        ],
        "footer": {
            "text": f"{PROJECT_NAME} • {PROJECT_AUTHOR}",
        },
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if image_url:
        embed["thumbnail"] = {"url": image_url}

    payload = {
        "username": f"Wuwa Tappo Auto Claim (Desktop v{APP_VERSION})",
        "avatar_url": "https://aki-gm-resources-back.aki-game.net/head_photo/82001501.png",
        "embeds": [embed],
    }

    try:
        requests.post(webhook_url, json=payload, timeout=8)
    except Exception as e:
        logger.debug(f"Failed to send Discord webhook: {e}")


# ----------------- API CLIENT -----------------
class WuwaTappoClient:
    def __init__(self, token, cid):
        self.token = token
        self.cid = cid
        self.session = requests.Session()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-BLM-CID": self.cid,
            "X-BLM-FRID": uuid.uuid4().hex,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0",
            "Origin": "http://tauri.localhost",
            "Referer": "http://tauri.localhost/",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

    def try_refresh_token(self) -> bool:
        """Automatically find and reload fresh token from RAM or Cookies when expired."""
        new_tok = auto_detect_token_from_memory() or get_token_from_cookies()
        if new_tok and new_tok != self.token:
            logger.info(f"Token refreshed automatically: {new_tok[:8]}...{new_tok[-8:]}")
            self.token = new_tok
            save_config_key("token", new_tok)
            global tray_icon
            if tray_icon:
                try:
                    tray_icon.notify("Session token was refreshed automatically.", "Wuwa Tappo Auto Claim")
                except Exception:
                    pass
            return True
        return False

    def get_server_time(self):
        """Fetch Kuro server timestamp (called once on startup)."""
        r = self.session.get(f"{SERVICE_BASE}/api/common/activity-config", timeout=10)
        return r.json()["data"]["server_time"]

    def get_user_info(self):
        """Retrieve user account info (automatically retries if session expired)."""
        r = self.session.get(f"{SERVICE_BASE}/api/frontend/user/me", headers=self._headers(), timeout=10)
        res = r.json()
        if res.get("code") in (10002, 10003, 90002):
            logger.warning(f"User info query rejected ({res.get('code')}). Attempting automatic token refresh...")
            if self.try_refresh_token():
                r = self.session.get(f"{SERVICE_BASE}/api/frontend/user/me", headers=self._headers(), timeout=10)
                res = r.json()
            else:
                raise Exception("Session token expired! Please launch or log in to Wuwa Tappo.")
        if res.get("code") != 0:
            raise Exception(f"Account query error: {res.get('message', res)}")
        return res["data"]

    def open_chest(self, place, click_num):
        """Send chest claim request (automatically refreshes token on expiry)."""
        payload = {"place": place, "click_num": click_num}
        r = self.session.post(f"{SERVICE_BASE}/api/frontend/chests/open", headers=self._headers(), json=payload, timeout=10)
        res = r.json()
        if res.get("code") in (10002, 10003, 90002):
            logger.warning(f"Claim request rejected ({res.get('code')}). Attempting automatic token refresh...")
            if self.try_refresh_token():
                r = self.session.post(f"{SERVICE_BASE}/api/frontend/chests/open", headers=self._headers(), json=payload, timeout=10)
                res = r.json()
        return res


def format_duration(seconds: int) -> str:
    """Format seconds into '00m 00s' string."""
    m, s = divmod(max(0, int(seconds)), 60)
    if m > 0:
        return f"{m:02d}m {s:02d}s"
    return f"{s:02d}s"


def ts_to_str(ts_ms: int) -> str:
    """Convert millisecond timestamp into HH:MM:SS."""
    if ts_ms <= 0:
        return "READY"
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000)
    return dt.strftime("%H:%M:%S")


def is_app_running() -> bool:
    """Check if Wuwa Tappo desktop pet application is currently running."""
    my_pid = os.getpid()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            name = (p.info["name"] or "").lower()
            if name == "wuwatappo.exe":
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


POLICY_KEY = r"SOFTWARE\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments"
CDP_PORT = 19222


def is_admin() -> bool:
    """Check if the process is running with Administrator privileges."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin():
    """Prompt Windows UAC dialog to request Administrator privileges if not elevated."""
    if os.name == "nt" and not is_admin():
        logger.info("Requesting Administrator elevation via UAC...")
        args_str = " ".join([f'"{a}"' for a in sys.argv[1:]])
        if getattr(sys, "frozen", False):
            params = args_str if args_str else None
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, WORKSPACE_DIR, 1
            )
        else:
            script = os.path.abspath(__file__)
            params = f'"{script}" {args_str}'.strip()
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, WORKSPACE_DIR, 1
            )
        sys.exit(0)


def setup_pet_sync():
    """Apply WebView2 debugging registry policy ONLY for WuwaTappo.exe."""
    if os.name != "nt":
        return
    arg = f"--remote-debugging-port={CDP_PORT}"
    try:
        key_lm = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, POLICY_KEY)
        winreg.SetValueEx(key_lm, "WuwaTappo.exe", 0, winreg.REG_SZ, arg)
        try:
            winreg.DeleteValue(key_lm, "*")
        except Exception:
            pass
        winreg.CloseKey(key_lm)
    except Exception as e:
        logger.debug(f"Failed to write HKLM policy: {e}")

    try:
        key_cu = winreg.CreateKey(winreg.HKEY_CURRENT_USER, POLICY_KEY)
        winreg.SetValueEx(key_cu, "WuwaTappo.exe", 0, winreg.REG_SZ, arg)
        try:
            winreg.DeleteValue(key_cu, "*")
        except Exception:
            pass
        winreg.CloseKey(key_cu)
    except Exception as e:
        logger.debug(f"Failed to write HKCU policy: {e}")


def cleanup_registry_policy():
    """Remove all WebView2 debugging registry keys (HKLM and HKCU) for a zero footprint.
    WebView2 only reads registry at boot, so keys can be safely cleared right after activation.
    """
    if os.name != "nt":
        return
    # 1. Clean HKLM Policy
    try:
        key_lm = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, POLICY_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key_lm, "WuwaTappo.exe")
        winreg.DeleteValue(key_lm, "*")
        winreg.CloseKey(key_lm)
    except Exception:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, POLICY_KEY)
    except Exception:
        pass

    # 2. Clean HKCU Policy
    try:
        key_cu = winreg.OpenKey(winreg.HKEY_CURRENT_USER, POLICY_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key_cu, "WuwaTappo.exe")
        winreg.DeleteValue(key_cu, "*")
        winreg.CloseKey(key_cu)
    except Exception:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, POLICY_KEY)
    except Exception:
        pass

    # 3. Clean environment variables if present
    try:
        env_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(env_key, "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS")
        winreg.CloseKey(env_key)
    except Exception:
        pass

    try:
        u_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(u_key, "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS")
        winreg.CloseKey(u_key)
    except Exception:
        pass


def cleanup_pet_sync():
    """Clean up registry entries, restore cursor visibility, and stop system tray on exit."""
    cleanup_registry_policy()

    try:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    except Exception:
        pass

    global tray_icon
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass


pet_sync_enabled = True


def restart_pet_if_needed():
    """Prompt user to restart Wuwa Tappo if running without CDP port attached."""
    global pet_sync_enabled
    if not is_app_running():
        return
    if is_cdp_ready():
        pet_sync_enabled = True
        return

    c = Color
    print(f"\n  {c.YELLOW}[?] Wuwa Tappo is running without Pet Auto-Reload (Port {CDP_PORT}).{c.RESET}")
    print(f"      Do you want to restart Wuwa Tappo to enable Pet Sync? [Y/n]: ", end="", flush=True)
    try:
        ans = input().strip().lower()
    except Exception:
        ans = "n"

    if ans not in ("", "y", "yes"):
        pet_sync_enabled = False
        cleanup_registry_policy()
        print(f"  {c.GRAY}[*] Skipped restart. Tool will run in standard mode (no Pet Sync).{c.RESET}\n")
        logger.info("User skipped Wuwa Tappo restart. Pet Auto-Reload inactive.")
        return

    pet_sync_enabled = True
    print(f"  {c.CYAN}[*] Restarting Wuwa Tappo to activate Pet Auto-Reload (Port {CDP_PORT})...{c.RESET}")
    logger.info(f"Restarting Wuwa Tappo with user confirmation to bind CDP port {CDP_PORT}...")
    app_exe = None
    tappo_pids = set()
    my_pid = os.getpid()

    # 1. Terminate only the actual WuwaTappo process
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            name = (p.info["name"] or "").lower()
            if name == "wuwatappo.exe":
                tappo_pids.add(p.info["pid"])
                if p.info.get("exe") and not app_exe:
                    app_exe = p.info["exe"]
                p.kill()
        except Exception:
            pass

    # 2. Terminate ONLY WebView2 sub-processes belonging to Wuwa Tappo
    for p in psutil.process_iter(["pid", "name", "ppid", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or []).lower()
            if "msedgewebview2" in name:
                if p.info["ppid"] in tappo_pids or "com.kuro.wuwatappo" in cmd:
                    p.kill()
        except Exception:
            pass

    time.sleep(1.5)

    if not app_exe or not os.path.exists(app_exe):
        candidates = [
            r"D:\Program Files\WuwaTappoGlobal\WuwaTappo.exe",
            r"C:\Program Files\WuwaTappoGlobal\WuwaTappo.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\WuwaTappoGlobal\WuwaTappo.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), r"WuwaTappoGlobal\WuwaTappo.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), r"WuwaTappoGlobal\WuwaTappo.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                app_exe = candidate
                break

    if app_exe and os.path.exists(app_exe):
        try:
            env = os.environ.copy()
            env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
            subprocess.Popen([app_exe], env=env)
            for _ in range(8):
                time.sleep(1)
                if is_cdp_ready():
                    cleanup_registry_policy()
                    print(f"  {c.GREEN}[+] Wuwa Tappo restarted with Port {CDP_PORT} active!{c.RESET}\n")
                    logger.info(f"Wuwa Tappo Pet CDP port {CDP_PORT} initialized successfully!")
                    break
        except Exception as e:
            logger.debug(f"Could not relaunch Wuwa Tappo: {e}")


def is_cdp_ready() -> bool:
    """Check if WebView2 CDP debugging port is accessible."""
    try:
        resp = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=0.5)
        return resp.status_code == 200
    except Exception:
        return False


def sync_pet_ui(gross: int = 0, consumed: int = 0, left_ts: int = 0, right_ts: int = 0) -> bool:
    """Synchronize pet state via CDP:
    Inject JS directly into Vue/Pinia store for zero flicker and instant update.
    Fallbacks to Page.reload if store injection fails.
    """
    if not is_app_running() or not is_cdp_ready():
        return False
    try:
        import websockets

        resp = requests.get(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1.0)
        targets = resp.json()

        patch_js = f"""
        (() => {{
            try {{
                const app = document.querySelector('#app');
                const pinia = app?.__vue_app__?.config?.globalProperties?.$pinia;
                const store = pinia?._s?.get('GlobalState');
                if (store && store.userInfo && typeof store.$patch === 'function') {{
                    const patchData = {{
                        userInfo: {{
                            ...store.userInfo,
                            total_click_count: {gross},
                            total_click_consume: {consumed}
                        }}
                    }};
                    if ({left_ts} > 0) patchData.userInfo.left_treasure_chest = {left_ts};
                    if ({right_ts} > 0) patchData.userInfo.right_treasure_chest = {right_ts};
                    store.$patch(patchData);
                    return true;
                }}
            }} catch (e) {{}}
            return false;
        }})();
        """

        synced = False
        for target in targets:
            url = target.get("url", "").lower()
            title = target.get("title", "").lower()
            ws_url = target.get("webSocketDebuggerUrl")

            if ws_url and ("tauri" in url or "wuwatappo" in title or "kuro" in url or "localhost" in url):
                async def _send(endpoint):
                    async with websockets.connect(endpoint, close_timeout=2) as ws:
                        if gross > 0 or consumed > 0:
                            eval_cmd = {
                                "id": 1,
                                "method": "Runtime.evaluate",
                                "params": {"expression": patch_js, "returnByValue": True},
                            }
                            await ws.send(json.dumps(eval_cmd))
                            res_raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                            res = json.loads(res_raw)
                            val = res.get("result", {}).get("result", {}).get("value")
                            if val is True:
                                return True

                        reload_cmd = {"id": 2, "method": "Page.reload", "params": {"ignoreCache": True}}
                        await ws.send(json.dumps(reload_cmd))
                        return True

                synced = asyncio.run(_send(ws_url)) or synced

        if synced:
            logger.info(f"[Sync] Wuwa Tappo Pet UI synchronized successfully via CDP port {CDP_PORT}!")
        return synced
    except Exception as e:
        logger.debug(f"CDP sync error: {e}")
        return False


def notify_app_refresh(gross: int = 0, consumed: int = 0, left_ts: int = 0, right_ts: int = 0):
    """Automatically refresh Pet state via DevTools CDP (Pinia store patch with reload fallback)."""
    if is_app_running() and is_cdp_ready():
        sync_pet_ui(gross=gross, consumed=consumed, left_ts=left_ts, right_ts=right_ts)


# Register automatic registry cleanup on process termination
atexit.register(cleanup_pet_sync)


def _signal_handler(sig, frame):
    cleanup_pet_sync()
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _signal_handler)
except Exception:
    pass

if os.name == "nt":
    try:
        _PHANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
        def _console_ctrl(ctrl_type):
            cleanup_pet_sync()
            return False
        _ctrl_proc = _PHANDLER(_console_ctrl)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_proc, True)
    except Exception:
        pass


def build_banner_lines() -> list:
    w = BOX_WIDTH
    c = Color
    title_text = f"{PROJECT_NAME} v{APP_VERSION}".upper()
    author_text = PROJECT_AUTHOR
    return [
        f"\n{c.CYAN}  ╔{'═' * (w - 2)}╗{c.RESET}",
        f"{c.CYAN}  ║{c.BOLD}{c.YELLOW}{title_text.center(w - 2)}{c.RESET}{c.CYAN}║{c.RESET}",
        f"{c.CYAN}  ║{c.GRAY}{author_text.center(w - 2)}{c.RESET}{c.CYAN}║{c.RESET}",
        f"{c.CYAN}  ╚{'═' * (w - 2)}╝{c.RESET}\n",
    ]


def build_dashboard_lines(
    nickname: str,
    balance: int,
    total_clicks: int,
    total_consume: int,
    left_ts: int,
    right_ts: int,
    now_ts: int,
    app_running: bool = False,
    token_str: str = "",
    cid_str: str = "",
    has_webhook: bool = False,
) -> list:
    c = Color
    left_cd = max(0, int((left_ts - now_ts) / 1000))
    right_cd = max(0, int((right_ts - now_ts) / 1000))

    left_status = f"{c.GREEN}READY TO CLAIM{c.RESET}" if left_cd == 0 else f"{c.WHITE}{ts_to_str(left_ts)}{c.RESET} {c.GRAY}(in {format_duration(left_cd)}){c.RESET}"
    right_status = f"{c.GREEN}READY TO CLAIM{c.RESET}" if right_cd == 0 else f"{c.WHITE}{ts_to_str(right_ts)}{c.RESET} {c.GRAY}(in {format_duration(right_cd)}){c.RESET}"
    if not app_running:
        sync_status = f"{c.GRAY}Idle (App Closed){c.RESET}"
    elif not pet_sync_enabled:
        sync_status = f"{c.YELLOW}Disabled by User (Port {CDP_PORT} Off){c.RESET}"
    elif is_cdp_ready():
        sync_status = f"{c.GREEN}Active (Pet Auto-Reload ON){c.RESET}"
    else:
        sync_status = f"{c.RED}Disconnected (Port {CDP_PORT} Off){c.RESET}"
    discord_status = f"{c.GREEN}Connected{c.RESET}" if has_webhook else f"{c.GRAY}Disabled{c.RESET}"

    version_status = f"{c.WHITE}v{APP_VERSION}{c.RESET} {c.GRAY}(Latest){c.RESET}"
    if latest_version_info:
        new_v = latest_version_info.get("version", "")
        version_status = f"{c.WHITE}v{APP_VERSION}{c.RESET} {c.BOLD}{c.GREEN}➜ New v{new_v} available!{c.RESET}"

    return [
        f"{c.CYAN}{make_top('Status Dashboard')}{c.RESET}",
        box_line(f"{c.YELLOW}Player{c.RESET}          : {c.BOLD}{c.WHITE}{nickname}{c.RESET}"),
        box_line(f"{c.YELLOW}Version{c.RESET}         : {version_status}"),
        box_line(f"{c.YELLOW}Balance{c.RESET}         : {c.BOLD}{c.GREEN}{balance:,} clicks{c.RESET} {c.GRAY}(Total: {total_clicks:,} | Spent: {total_consume:,}){c.RESET}"),
        f"{c.CYAN}{make_mid('Connection & System')}{c.RESET}",
        box_line(f"{c.YELLOW}Token{c.RESET}           : {c.WHITE}{token_str}{c.RESET}"),
        box_line(f"{c.YELLOW}Device{c.RESET}          : {c.WHITE}{cid_str}{c.RESET}"),
        box_line(f"{c.YELLOW}Discord Webhook{c.RESET} : {discord_status}"),
        box_line(f"{c.YELLOW}App Sync{c.RESET}        : {sync_status}"),
        box_line(f"{c.YELLOW}Tray Mode{c.RESET}       : {c.CYAN}Click [-] Minimize to hide to Tray{c.RESET}"),
        f"{c.CYAN}{make_mid('Cooldown Schedule')}{c.RESET}",
        box_line(f"{c.CYAN}[Left Chest]{c.RESET}    : {left_status}"),
        box_line(f"{c.CYAN}[Right Chest]{c.RESET}   : {right_status}"),
        f"{c.CYAN}{make_bot()}{c.RESET}\n",
    ]


def build_claim_card_lines(chest_count: int, place: str, asset: str, rarity: str, balance: int, next_cd: int) -> list:
    c = Color
    place_name = "Left Chest" if place == "left" else "Right Chest"
    rarity_style = c.RARITY.get(rarity.lower(), c.WHITE)

    title = f"★ REWARD CLAIMED (#{chest_count})"
    return [
        f"{c.GREEN}{make_top(title)}{c.RESET}",
        box_line(f"{c.YELLOW}Chest{c.RESET}   : {c.BOLD}{place_name}{c.RESET}"),
        box_line(f"{c.YELLOW}Item{c.RESET}    : {c.BOLD}{c.WHITE}{asset}{c.RESET} {rarity_style}({rarity.capitalize()}){c.RESET}"),
        box_line(f"{c.YELLOW}Balance{c.RESET} : {c.BOLD}{c.GREEN}{balance:,} clicks{c.RESET} {c.GRAY}| Next: {format_duration(next_cd)}{c.RESET}"),
        f"{c.GREEN}{make_bot()}{c.RESET}\n",
    ]


def clear_terminal():
    """Clear terminal console screen and position cursor at top-left corner."""
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def redraw_screen(
    nickname: str,
    balance: int,
    total_clicks: int,
    total_consume: int,
    left_ts: int,
    right_ts: int,
    now_ts: int,
    app_running: bool,
    token_str: str = "",
    cid_str: str = "",
    has_webhook: bool = False,
    last_reward: dict = None,
    progress_line: str = "",
    in_place: bool = False,
):
    """Refresh entire terminal screen or render in-place for flicker-free countdown updates."""
    global is_window_visible
    if not is_window_visible:
        return

    lines = []
    lines.extend(build_banner_lines())
    lines.extend(build_dashboard_lines(
        nickname=nickname,
        balance=balance,
        total_clicks=total_clicks,
        total_consume=total_consume,
        left_ts=left_ts,
        right_ts=right_ts,
        now_ts=now_ts,
        app_running=app_running,
        token_str=token_str,
        cid_str=cid_str,
        has_webhook=has_webhook,
    ))
    if last_reward:
        lines.extend(build_claim_card_lines(
            chest_count=last_reward["count"],
            place=last_reward["place"],
            asset=last_reward["asset"],
            rarity=last_reward["rarity"],
            balance=last_reward["balance"],
            next_cd=last_reward["next_cd"],
        ))
    if progress_line:
        lines.append(progress_line)

    content = "\n".join(lines)
    if in_place:
        sys.stdout.write("\033[H" + content + "   \n")
    else:
        clear_terminal()
        sys.stdout.write(content + "\n")
    sys.stdout.flush()


# ----------------- MAIN LOOP -----------------
def main():
    ensure_admin()
    setup_pet_sync()
    init_terminal()
    render_banner()
    restart_pet_if_needed()
    cleanup_registry_policy()

    token, cid, webhook_url, token_src, cid_src, show_window_cfg = load_config()
    client = WuwaTappoClient(token, cid)

    # Check for new updates in background 5 minutes after startup
    threading.Thread(target=delayed_update_check, daemon=True).start()

    # Initialize System Tray Icon & Window monitor thread
    init_tray()
    if os.name == "nt":
        threading.Thread(target=window_monitor_loop, daemon=True).start()

    token_str = f"{token[:8]}...{token[-8:]} ({token_src})"
    cid_str = f"{cid[:6]}...{cid[-6:]} ({cid_src})"
    has_webhook = bool(webhook_url)

    # 1. Synchronize clock with Kuro server once at startup
    print(f"  {Color.GRAY}[*] Synchronizing clock with Kuro server...{Color.RESET}")
    try:
        server_time_init = client.get_server_time()
        local_time_init = time.time() * 1000
        time_offset = server_time_init - local_time_init
        logger.info(f"Server time synchronized. Offset: {time_offset:+.1f}ms")
    except Exception as e:
        print(f"  {Color.RED}[-] Clock sync failed: {e}{Color.RESET}")
        logger.error(f"Clock sync failed: {e}")
        time_offset = 0

    def current_server_ts():
        """Get current server timestamp from local clock + calculated offset (0 network requests)."""
        return time.time() * 1000 + time_offset

    # 2. Retrieve initial account state
    try:
        user = client.get_user_info()
    except Exception as e:
        print(f"  {Color.RED}[-] Failed to load user account: {e}{Color.RESET}")
        logger.error(f"Failed to load user account: {e}")
        input("\nPress Enter to exit...")
        return

    nickname = user.get("nickname", "User")
    total_clicks = user.get("total_click_count", 0)
    total_consume = user.get("total_click_consume", 0)
    left_ts = user.get("left_treasure_chest", 0)
    right_ts = user.get("right_treasure_chest", 0)

    chest_count = 0
    last_reward = None
    app_running = is_app_running()

    def update_view(override_reward=None, progress_line="", in_place=False):
        redraw_screen(
            nickname=nickname,
            balance=total_clicks - total_consume,
            total_clicks=total_clicks,
            total_consume=total_consume,
            left_ts=left_ts,
            right_ts=right_ts,
            now_ts=current_server_ts(),
            app_running=app_running,
            token_str=token_str,
            cid_str=cid_str,
            has_webhook=has_webhook,
            last_reward=override_reward if override_reward is not None else last_reward,
            progress_line=progress_line,
            in_place=in_place,
        )

    global global_update_view_fn
    global_update_view_fn = update_view

    update_view()

    # Apply show_window setting from config on startup
    if not show_window_cfg:
        hide_window(notify_user=False)

    last_chest_open_total = {}
    claim_failures = {"left": 0, "right": 0}

    while running_flag:
        try:
            now = current_server_ts()
            left_cd = max(0, int((left_ts - now) / 1000))
            right_cd = max(0, int((right_ts - now) / 1000))

            # 3. Check if any chest is ready to open
            chest_to_open = None
            if left_cd == 0:
                chest_to_open = "left"
            elif right_cd == 0:
                chest_to_open = "right"

            if chest_to_open:
                # Clear countdown line before printing claim card
                sys.stdout.write("\r" + " " * 75 + "\r")
                sys.stdout.flush()

                app_running = is_app_running()

                # Always sync latest user state before claiming to prevent stale click counts
                try:
                    u = client.get_user_info()
                    if client.token != token:
                        token = client.token
                        token_str = f"{token[:8]}...{token[-8:]} (Auto-Refreshed)"
                    total_clicks = u.get("total_click_count", total_clicks)
                    total_consume = u.get("total_click_consume", total_consume)
                    left_ts = u.get("left_treasure_chest", left_ts)
                    right_ts = u.get("right_treasure_chest", right_ts)
                    # Re-verify cooldown in case of server-side timing drift
                    now = current_server_ts()
                    if chest_to_open == "left" and left_ts > now:
                        update_view()
                        time.sleep(1)
                        continue
                    if chest_to_open == "right" and right_ts > now:
                        update_view()
                        time.sleep(1)
                        continue
                except Exception as e:
                    logger.debug(f"Pre-claim user info sync failed: {e}")

                target_click = total_clicks + CLICK_GAIN_PER_CHEST
                min_needed = (total_consume + CHEST_COST) + MIN_BALANCE_MAINTAIN
                if target_click < min_needed:
                    target_click = min_needed

                place_name = "Left Chest" if chest_to_open == "left" else "Right Chest"
                sys.stdout.write(f"\r  {Color.YELLOW}[*] Claiming {place_name}...{' ' * 35}\r")
                sys.stdout.flush()
                logger.info(f"Claiming {place_name} (Reported clicks: {target_click:,})...")

                res = client.open_chest(chest_to_open, target_click)
                if client.token != token:
                    token = client.token
                    token_str = f"{token[:8]}...{token[-8:]} (Auto-Refreshed)"

                if res.get("code") == 0:
                    claim_failures[chest_to_open] = 0
                    chest_count += 1
                    data = res.get("data", {})
                    asset = data.get("asset_name", "Unknown")
                    rarity = data.get("rarity_type", "common")
                    consume = data.get("click_consume", CHEST_COST)

                    total_clicks = target_click
                    total_consume += consume

                    new_left = data.get("left_next_time", 0)
                    new_right = data.get("right_next_time", 0)
                    if new_left > 0:
                        left_ts = new_left
                    if new_right > 0:
                        right_ts = new_right

                    next_cd = int((new_left if chest_to_open == "left" else new_right) - current_server_ts()) // 1000
                    last_chest_open_total[chest_to_open] = max(1, next_cd)

                    last_reward = {
                        "count": chest_count,
                        "place": chest_to_open,
                        "asset": asset,
                        "rarity": rarity,
                        "balance": total_clicks - total_consume,
                        "next_cd": next_cd,
                    }

                    logger.info(
                        f"SUCCESS #{chest_count}: {asset} ({rarity})! "
                        f"New balance: {total_clicks - total_consume:,}"
                    )

                    send_discord_webhook(
                        webhook_url=webhook_url,
                        nickname=nickname,
                        place=chest_to_open,
                        asset_name=asset,
                        rarity=rarity,
                        balance=total_clicks - total_consume,
                        left_wait_sec=max(0, int((left_ts - current_server_ts()) / 1000)),
                        right_wait_sec=max(0, int((right_ts - current_server_ts()) / 1000)),
                    )

                    # Trigger pet UI synchronization to reload WebView2 state
                    if is_app_running():
                        notify_app_refresh(
                            gross=total_clicks,
                            consumed=total_consume,
                            left_ts=left_ts,
                            right_ts=right_ts,
                        )

                    update_view(last_reward)
                    time.sleep(1)
                    continue
                else:
                    err_msg = res.get("message", str(res))
                    sys.stdout.write(f"\r  {Color.RED}[!] Failed to claim {place_name}: {err_msg}{' ' * 10}\r")
                    sys.stdout.flush()
                    logger.warning(f"Failed to claim {place_name}: {err_msg}")
                    claim_failures[chest_to_open] = claim_failures.get(chest_to_open, 0) + 1
                    try:
                        u = client.get_user_info()
                        if client.token != token:
                            token = client.token
                            token_str = f"{token[:8]}...{token[-8:]} (Auto-Refreshed)"
                        total_clicks = u.get("total_click_count", total_clicks)
                        total_consume = u.get("total_click_consume", total_consume)
                        left_ts = u.get("left_treasure_chest", left_ts)
                        right_ts = u.get("right_treasure_chest", right_ts)
                    except Exception:
                        pass

                    if claim_failures[chest_to_open] >= 3:
                        logger.warning(f"Repeated failures for {place_name}. Adding 30s cooldown buffer...")
                        if chest_to_open == "left":
                            left_ts = now + 30000
                        else:
                            right_ts = now + 30000
                        claim_failures[chest_to_open] = 0

                    update_view()
                    time.sleep(2)
                    continue

            # 4. When both chests are in cooldown
            next_wait = min(left_cd, right_cd)
            next_name = "Left Chest" if left_cd <= right_cd else "Right Chest"
            chest_key = "left" if left_cd <= right_cd else "right"
            total_duration = last_chest_open_total.get(chest_key, 1800)

            # Update countdown progress bar every second (0 network requests)
            sync_timer = 0
            while next_wait > 0 and running_flag:
                # Check local Wuwa Tappo running state every 5 seconds (0 network requests)
                if sync_timer % 5 == 0:
                    was_running = app_running
                    app_running = is_app_running()

                elapsed = max(0, total_duration - next_wait)
                pct = min(1.0, elapsed / max(1, total_duration))
                bar_len = 16
                filled = int(pct * bar_len)
                bar = "■" * filled + "□" * (bar_len - filled)

                timer_str = format_duration(next_wait)
                line = (
                    f"  {Color.CYAN}>> Next:{Color.RESET} {Color.WHITE}{next_name}{Color.RESET} "
                    f"in {Color.YELLOW}{timer_str}{Color.RESET} "
                    f"[{Color.GREEN}{bar}{Color.RESET}]"
                )

                update_view(progress_line=line, in_place=True)

                time.sleep(1)
                next_wait -= 1
                sync_timer += 1

            sys.stdout.write("\r" + " " * 75 + "\r")
            sys.stdout.flush()

        except KeyboardInterrupt:
            print(f"\n\n  {Color.YELLOW}[*] Auto Claim stopped by user. Goodbye!{Color.RESET}\n")
            logger.info("Program stopped by user.")
            break
        except Exception as e:
            print(f"\n  {Color.RED}[!] Unexpected error: {e}{Color.RESET}")
            logger.error(f"Unexpected exception: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pet_sync()

"""Wuwa Tappo Token Extractor (Desktop)
Author: github.com/Triet2804Dev
Extracts token and device CID from WebView2 Cookies storage or process RAM,
with automatic clipboard copy and matching terminal dashboard UI.
"""

import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import psutil

# ----------------- CONSTANTS & PATHS -----------------
PROJECT_NAME = "Wuwa Tappo Token Extractor"
PROJECT_AUTHOR = "github.com/Triet2804Dev"
BOX_WIDTH = 70

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32


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


def init_terminal():
    """Enable ANSI Escape Code support on Windows Terminal / cmd.exe."""
    if os.name == "nt":
        try:
            h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(h_stdout, mode.value | 0x0004)
            kernel32.SetConsoleTitleW(f"{PROJECT_NAME} - {PROJECT_AUTHOR}")
        except Exception:
            pass


ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(s: str) -> int:
    """Calculate visible string length after stripping ANSI color codes."""
    return len(ANSI_REGEX.sub("", s))


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


# ----------------- CLIPBOARD HELPER -----------------
def copy_to_clipboard(text: str) -> bool:
    """Copy given text to Windows clipboard via native Win32 API."""
    if os.name != "nt":
        return False
    try:
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.EmptyClipboard.argtypes = []
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []

        CF_UNICODETEXT = 13
        GHND = 0x0042
        data = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GHND, len(data))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(None):
            return False
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()
        return True
    except Exception:
        return False


# ----------------- TOKEN AUTO-DECRYPTION FROM COOKIES -----------------
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def get_token_from_cookies():
    """Decrypt kuro_infoToken from WebView2 Cookies storage.
    Supports Chromium v24+ schema (validates and strips 32-byte SHA256(host) prefix).
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
        kernel32.LocalFree(blob_out.pbData)

        temp_cookies = os.path.join(os.environ.get("TEMP", ""), f"wuwatappo_ck_{uuid.uuid4().hex[:8]}.db")
        try:
            shutil.copy2(cookies_path, temp_cookies)
        except Exception:
            return None

        conn = sqlite3.connect(temp_cookies)
        cur = conn.cursor()

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

                if version >= 24:
                    expected_prefix = hashlib.sha256(host.encode("utf-8")).digest()
                    if decrypted[:32] == expected_prefix:
                        decrypted = decrypted[32:]

                token = decrypted.decode("utf-8", errors="ignore").strip()
                if re.fullmatch(r"[a-f0-9]{64}", token):
                    return token

                m = re.search(rb"([a-f0-9]{64})", decrypted)
                if m:
                    return m.group(1).decode("utf-8")
    except Exception:
        pass
    return None


# ----------------- TOKEN EXTRACTION FROM RAM -----------------
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


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
    """Retrieve X-BLM-CID from LocalStorage LevelDB."""
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


def get_token_from_config():
    """Fallback: read token from config.json if present in parent directories."""
    candidates = [
        "config.json",
        os.path.join("..", "config.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    tok = cfg.get("token", "")
                    if tok and not tok.startswith("dpapi:"):
                        return tok
            except Exception:
                pass
    return None


# ----------------- MAIN EXECUTION -----------------
def main():
    init_terminal()
    render_banner()

    c = Color
    print(f"  {c.GRAY}[*] Scanning system for Wuwa Tappo credentials...{c.RESET}")

    token = None
    token_source = None
    cid = auto_detect_cid()

    # Step 1: Scan Process Memory (fastest & works directly while Wuwa Tappo is running)
    token = auto_detect_token_from_memory()
    if token:
        token_source = "Process RAM (Wuwa Tappo)"
    else:
        # Step 2: Check WebView2 Cookies (works when Wuwa Tappo is closed)
        token = get_token_from_cookies()
        if token:
            token_source = "WebView2 Cookies"
        else:
            # Step 3: Check config.json
            token = get_token_from_config()
            if token:
                token_source = "config.json"

    print()

    if token:
        # Auto-copy to clipboard
        copied = copy_to_clipboard(token)

        masked_token = f"{token[:8]}...{token[-8:]}" if len(token) >= 16 else token
        masked_cid = f"{cid[:8]}...{cid[-8:]}" if (cid and len(cid) >= 16) else (cid or "Not Found")

        print(f"{c.CYAN}{make_top('Credentials Found')}{c.RESET}")
        print(f"{c.CYAN}{box_line(f'{c.WHITE}Status     : {c.GREEN}Success!{c.RESET}')}{c.RESET}")
        print(f"{c.CYAN}{box_line(f'{c.WHITE}Source     : {c.YELLOW}{token_source}{c.RESET}')}{c.RESET}")
        print(f"{c.CYAN}{box_line(f'{c.WHITE}Device CID : {c.CYAN}{masked_cid}{c.RESET}')}{c.RESET}")
        print(f"{c.CYAN}{box_line(f'{c.WHITE}Token      : {c.YELLOW}{masked_token}{c.RESET}')}{c.RESET}")
        print(f"{c.CYAN}{make_mid('Raw Token')}{c.RESET}")

        # Split 64-char token nicely if needed or display directly
        print(f"{c.CYAN}{box_line(f'{c.BOLD}{c.YELLOW}{token}{c.RESET}')}{c.RESET}")
        print(f"{c.CYAN}{make_bot()}{c.RESET}")
        print()

        if copied:
            print(f"  {c.BOLD}{c.GREEN}[✓] Token automatically copied to your clipboard!{c.RESET}")
        else:
            print(f"  {c.YELLOW}[!] Could not access clipboard automatically. Please copy the token above.{c.RESET}")

        print(f"  {c.GRAY}[i] You can now paste this token directly into CONFIG.TOKEN in Google Apps Script.{c.RESET}\n")

    else:
        print(f"{c.RED}{make_top('Token Not Found')}{c.RESET}")
        print(f"{c.RED}{box_line(f'{c.WHITE}Status     : {c.RED}Failed to detect token{c.RESET}')}{c.RESET}")
        print(f"{c.RED}{make_mid('Troubleshooting Tips')}{c.RESET}")
        print(f"{c.RED}{box_line(f'{c.YELLOW}1. Open the Wuwa Tappo Desktop App and log in once.{c.RESET}')}{c.RESET}")
        print(f"{c.RED}{box_line(f'{c.YELLOW}2. Keep the app open and run this tool again.{c.RESET}')}{c.RESET}")
        print(f"{c.RED}{box_line(f'{c.YELLOW}3. Or use the browser F12 Console script (get_token.js).{c.RESET}')}{c.RESET}")
        print(f"{c.RED}{make_bot()}{c.RESET}")
        print()

    try:
        input(f"  {c.GRAY}Press Enter to exit...{c.RESET}")
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()

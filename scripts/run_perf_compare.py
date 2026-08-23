"""Launcher for perf_compare_raw.py using fresh cookies from D:/BiliStalkerSecrets.

Env vars take precedence over .env (load_dotenv override=False), so exporting
the cookie file fields here gives both benchmark groups the same valid login.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

COOKIE_FILE = Path(r"D:\BiliStalkerSecrets\bili-cookie.txt")
FIELD_TO_ENV = {
    "SESSDATA": "SESSDATA",
    "bili_jct": "BILI_JCT",
    "buvid3": "BUVID3",
    "buvid4": "BUVID4",
    "DedeUserID": "DEDEUSERID",
}

ENV = {
    "BILI_BENCH_PROXY": "http://127.0.0.1:50888",
    "BILI_412_CIRCUIT_THRESHOLD": "999",  # keep both groups symmetric under 412 noise
}


def parse_cookies(text: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in re.split(r"[;\n]", text):
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def main() -> int:
    cookies = parse_cookies(COOKIE_FILE.read_text(encoding="utf-8"))
    env = dict(os.environ)
    for field, env_name in FIELD_TO_ENV.items():
        if field in cookies:
            env[env_name] = cookies[field]
    env.update(ENV)

    script = Path(__file__).with_name("perf_compare_raw.py")
    return subprocess.call([sys.executable, str(script), *sys.argv[1:]], env=env)


if __name__ == "__main__":
    raise SystemExit(main())

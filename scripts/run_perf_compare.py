"""Launcher for perf_compare_raw.py using a real login cookie file.

Env-driven so other machines don't inherit this one's paths:

- BILI_BENCH_COOKIE_FILE  cookie file to read credentials from
  (default: D:\\BiliStalkerSecrets\\bili-cookie.txt, this project's dev box)
- BILI_BENCH_PROXY        optional proxy, e.g. http://127.0.0.1:50888;
                          unset means "no forced proxy"

Env vars take precedence over .env (load_dotenv override=False), so exporting
the cookie file fields here gives both benchmark groups the same valid login.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_COOKIE_FILE = Path(r"D:\BiliStalkerSecrets\bili-cookie.txt")
FIELD_TO_ENV = {
    "SESSDATA": "SESSDATA",
    "bili_jct": "BILI_JCT",
    "buvid3": "BUVID3",
    "buvid4": "BUVID4",
    "DedeUserID": "DEDEUSERID",
}


def parse_cookies(text: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in re.split(r"[;\n]", text):
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def main() -> int:
    cookie_file = Path(os.environ.get("BILI_BENCH_COOKIE_FILE") or DEFAULT_COOKIE_FILE)
    if not cookie_file.is_file():
        print(
            f"Cookie file not found: {cookie_file} "
            "(set BILI_BENCH_COOKIE_FILE to override)",
            file=sys.stderr,
        )
        return 2

    cookies = parse_cookies(cookie_file.read_text(encoding="utf-8"))
    env = dict(os.environ)
    for field, env_name in FIELD_TO_ENV.items():
        if field in cookies:
            env[env_name] = cookies[field]

    # Keep both groups symmetric when occasional 412s appear mid-benchmark.
    env.setdefault("BILI_412_CIRCUIT_THRESHOLD", "999")

    bench_proxy = os.environ.get("BILI_BENCH_PROXY", "").strip()
    if bench_proxy:
        env["BILI_BENCH_PROXY"] = bench_proxy

    script = Path(__file__).with_name("perf_compare_raw.py")
    return subprocess.call([sys.executable, str(script), *sys.argv[1:]], env=env)


if __name__ == "__main__":
    raise SystemExit(main())

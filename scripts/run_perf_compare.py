"""Launcher for perf_compare_raw.py using a real login cookie file.

Configure credential paths for the machine running the benchmark:

- BILI_BENCH_COOKIE_FILE  cookie file to read credentials from
  (falls back to BILI_COOKIE_FILE; one of the two must be set)
- BILI_BENCH_PROXY        optional proxy, e.g. http://127.0.0.1:8080;
                          unset means "no forced proxy"

Env vars take precedence over .env (load_dotenv override=False), so exporting
the cookie file fields here gives both benchmark groups the same valid login.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

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
    cookie_path = (
        os.environ.get("BILI_BENCH_COOKIE_FILE", "").strip()
        or os.environ.get("BILI_COOKIE_FILE", "").strip()
    )
    if not cookie_path:
        print(
            "Set BILI_BENCH_COOKIE_FILE or BILI_COOKIE_FILE to a Cookie file "
            "on this machine.",
            file=sys.stderr,
        )
        return 2
    cookie_file = Path(cookie_path).expanduser()
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

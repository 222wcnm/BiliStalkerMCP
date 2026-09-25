"""Install the built wheel in a clean environment and exercise its CLI."""

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    expected = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    wheels = list((root / "dist").glob(f"bili_stalker_mcp-{expected}-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one wheel for {expected}, found {len(wheels)}")

    with tempfile.TemporaryDirectory(prefix="bili-wheel-smoke-") as temporary:
        workspace = Path(temporary)
        venv = workspace / "venv"
        subprocess.run(
            ["uv", "--quiet", "venv", str(venv), "--python", sys.executable],
            check=True,
        )
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cli = venv / (
            "Scripts/bili-stalker-mcp.exe"
            if os.name == "nt"
            else "bin/bili-stalker-mcp"
        )
        subprocess.run(
            [
                "uv",
                "--quiet",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheels[0]),
            ],
            check=True,
        )

        env = {**os.environ, "BILI_ENABLE_COOKIE_REFRESH": "false"}
        env.pop("PYTHONPATH", None)
        env.pop("BILI_PROXY", None)
        env.pop("BILI_COOKIE_FILE", None)
        env.pop("BILI_REFRESH_TOKEN_FILE", None)
        env["SESSDATA"] = "wheel-smoke-placeholder"

        def run(*arguments: str) -> str:
            return subprocess.check_output(
                arguments, cwd=workspace, env=env, text=True, encoding="utf-8"
            ).strip()

        if run(str(cli), "--version") != expected:
            raise RuntimeError("Installed CLI reported the wrong version")
        if not json.loads(run(str(cli), "doctor"))["ok"]:
            raise RuntimeError("Installed CLI doctor reported an unhealthy environment")
        for command in (
            (str(cli), "tools"),
            (str(python), "-m", "bili_stalker_mcp", "tools"),
        ):
            names = {tool["name"] for tool in json.loads(run(*command))}
            if len(names) != 12 or "get_user_snapshot" not in names:
                raise RuntimeError(
                    "Installed package did not expose the expected tools"
                )

    print("Installed wheel CLI smoke test passed")


if __name__ == "__main__":
    main()

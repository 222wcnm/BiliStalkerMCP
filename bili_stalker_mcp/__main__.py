"""
This module is the entry point for the `python -m BiliStalkerMCP` command.
It simply delegates to the `main` function in `cli.py`.
"""
from .cli import main

if __name__ == "__main__":
    main()

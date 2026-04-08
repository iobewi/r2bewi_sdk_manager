"""
role:
    Package entry point — delegates unconditionally to cli.main().

reading_order:
    1. src/cli.py — all logic starts there
"""
from .cli import main

main()

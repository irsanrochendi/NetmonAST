#!/usr/bin/env python3
"""
NetMon Alembic Migration Helper
================================
Commands:
    python manage_migrations.py init       — Initialize alembic (first time)
    python manage_migrations.py migrate    — Auto-generate migration from model changes
    python manage_migrations.py upgrade    — Run all pending migrations
    python manage_migrations.py downgrade  — Rollback one revision
    python manage_migrations.py history    — Show migration history
    python manage_migrations.py reset      — Reset database (drop all, recreate)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = SCRIPT_DIR


def run_alembic(command: str, *args) -> int:
    """Run an alembic command. Returns exit code."""
    cmd = [sys.executable, "-m", "alembic", command] + list(args)
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BACKEND_DIR)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="NetMon Migration Manager")
    parser.add_argument(
        "action",
        choices=["init", "migrate", "upgrade", "downgrade", "history", "reset", "status"],
        help="Migration action",
    )
    parser.add_argument("--message", "-m", default="auto migration", help="Migration message")
    parser.add_argument("--revision", "-r", default="head", help="Target revision")
    args = parser.parse_args()

    if args.action == "init":
        # Already done — alembic directory exists
        print("Alembic already initialized. Use 'migrate' to generate new migrations.")
        return 0

    elif args.action == "migrate":
        return run_alembic("revision", "--autogenerate", "-m", args.message)

    elif args.action == "upgrade":
        return run_alembic("upgrade", args.revision)

    elif args.action == "downgrade":
        target = args.revision if args.revision != "head" else "-1"
        return run_alembic("downgrade", target)

    elif args.action == "history":
        return run_alembic("history", "--verbose")

    elif args.action == "status":
        return run_alembic("current")

    elif args.action == "reset":
        print("⚠️  This will DROP ALL DATA and recreate the schema!")
        confirm = input("Type 'yes' to confirm: ")
        if confirm != "yes":
            print("Aborted.")
            return 1
        # Downgrade to base then upgrade
        run_alembic("downgrade", "base")
        return run_alembic("upgrade", "head")

    return 0


if __name__ == "__main__":
    sys.exit(main())

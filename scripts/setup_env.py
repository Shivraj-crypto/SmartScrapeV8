from __future__ import annotations

import argparse
import subprocess
import sys
from shutil import which

MIN_PYTHON = (3, 10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap local development dependencies for SmartScrapeV8."
    )
    parser.add_argument(
        "--skip-browser-install",
        action="store_true",
        help="Skip Scrapling browser/runtime installation.",
    )
    return parser.parse_args()


def check_python_version() -> bool:
    return sys.version_info >= MIN_PYTHON


def install_scrapling_runtime() -> int:
    executable = which("scrapling")
    if executable is None:
        print("Scrapling CLI not found on PATH; skipping browser/runtime installation.")
        return 0

    command = [executable, "install", "--force"]
    print(f"Running: {' '.join(command)}")
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    args = parse_args()

    if not check_python_version():
        print(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required. "
            f"Detected: {sys.version.split()[0]}"
        )
        return 1

    print("Python version check passed.")

    if args.skip_browser_install:
        print("Skipped Scrapling browser/runtime installation.")
        return 0

    exit_code = install_scrapling_runtime()
    if exit_code != 0:
        print("Scrapling browser/runtime installation failed.")
        return exit_code

    print("Scrapling browser/runtime installation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

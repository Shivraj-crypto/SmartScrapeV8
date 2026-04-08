from __future__ import annotations

import argparse
import subprocess
import sys

MIN_PYTHON = (3, 10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap local development dependencies for SmartScrapeV8."
    )
    parser.add_argument(
        "--browser",
        default="chromium",
        help="Playwright browser to install (default: chromium).",
    )
    parser.add_argument(
        "--skip-browser-install",
        action="store_true",
        help="Skip Playwright browser installation.",
    )
    return parser.parse_args()


def check_python_version() -> bool:
    return sys.version_info >= MIN_PYTHON


def install_playwright_browser(browser: str) -> int:
    # Using the active interpreter ensures installation happens in the same env.
    command = [sys.executable, "-m", "playwright", "install", browser]
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
        print("Skipped Playwright browser installation.")
        return 0

    exit_code = install_playwright_browser(args.browser)
    if exit_code != 0:
        print("Playwright browser installation failed.")
        return exit_code

    print("Playwright browser installation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

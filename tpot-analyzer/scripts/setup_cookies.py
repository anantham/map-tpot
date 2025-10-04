"""Interactive helper to capture Twitter/X authentication cookies."""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path
from typing import Optional

from selenium import webdriver


DEFAULT_OUTPUT = Path("secrets/twitter_cookies.pkl")


def build_driver(*, headless: bool = False, window_size: str = "1200,1200") -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={window_size}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Twitter/X cookies for Selenium sessions")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Where to write the cookies pickle (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headless (not recommended because you must log in manually)",
    )
    parser.add_argument(
        "--window-size",
        type=str,
        default="1200,1200",
        help="Window size passed to Chrome (WIDTH,HEIGHT)",
    )
    return parser.parse_args()


def capture_cookies(output_path: Path, *, headless: bool, window_size: str) -> Optional[Path]:
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    driver = build_driver(headless=headless, window_size=window_size)
    try:
        print("Opening https://twitter.com/login ...")
        driver.get("https://twitter.com/login")
        print("\nPlease complete login in the browser window.")
        print("When the session is ready, press Enter here to capture cookies.")
        input("Press Enter once you are logged in and the timeline is visible...")

        cookies = driver.get_cookies() or []
        if not cookies:
            print("\n✗ No cookies were captured. Is the session still active?")
            return None

        with output_path.open("wb") as fh:
            pickle.dump(cookies, fh)
        print(f"\n✓ Saved {len(cookies)} cookies to {output_path}")
        return output_path
    finally:
        driver.quit()


def main() -> None:
    args = parse_args()
    capture_cookies(args.output, headless=args.headless, window_size=args.window_size)


if __name__ == "__main__":
    main()

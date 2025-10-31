#!/usr/bin/env python3
"""
Test script to directly test list member scraping with diagnostics
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.shadow.selenium_worker import SeleniumWorker, SeleniumWorkerConfig
from src.logging_utils import setup_logging

def main():
    # Setup logging with DEBUG level
    setup_logging(log_level=logging.DEBUG)

    # Create selenium worker with a known cookie file
    config = SeleniumWorkerConfig(
        headless=False,  # Show browser for debugging
        scroll_delay_min=1.0,
        scroll_delay_max=2.0,
        max_no_change_scrolls=5
    )

    cookie_file = project_root / "secrets" / "twitter_cookies_aditya.pkl"

    print("Initializing Selenium worker...")
    worker = SeleniumWorker(config, cookie_file)

    try:
        print("\nYou have 30 seconds to verify login if needed...")
        print("Press Ctrl+C to skip if already logged in\n")
        import time
        time.sleep(30)
    except KeyboardInterrupt:
        print("Continuing...")

    # Test the list member fetching
    list_id = "1788441465326064008"
    print(f"\nFetching members from list {list_id}...")

    result = worker.fetch_list_members(list_id)

    print(f"\n✅ Captured {len(result.entries)} members")
    if result.claimed_total:
        print(f"📊 List claims to have {result.claimed_total} total members")
        print(f"📈 Coverage: {len(result.entries)}/{result.claimed_total} = {len(result.entries)/result.claimed_total*100:.1f}%")

    print("\n📝 First 10 members:")
    for i, entry in enumerate(result.entries[:10], 1):
        print(f"  {i}. @{entry.username} - {entry.display_name}")

    worker.cleanup()
    print("\n✅ Test completed")

if __name__ == "__main__":
    main()
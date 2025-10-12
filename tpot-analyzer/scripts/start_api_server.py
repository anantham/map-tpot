#!/usr/bin/env python
"""Start the Flask API server for graph-explorer."""
from __future__ import annotations

import argparse
import logging

from src.api.server import run_dev_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Flask API server")
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port to bind to (default: 5001)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in debug mode",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print(f"🚀 Starting Flask API server on http://{args.host}:{args.port}")
    print(f"📊 Graph Explorer frontend should connect to this endpoint")
    print(f"🔧 Debug mode: {args.debug}")
    print()

    run_dev_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

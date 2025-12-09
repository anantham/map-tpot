import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.api.server import create_app

def parse_args():
    parser = argparse.ArgumentParser(description="Start the TPOT Analyzer API server")
    parser.add_argument(
        "--host", 
        default="127.0.0.1", 
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=5001, 
        help="Port to bind to (default: 5001)"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable Flask debug mode"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Configure logging level via environment if not set
    if not os.getenv("API_LOG_LEVEL"):
        os.environ["API_LOG_LEVEL"] = "DEBUG" if args.debug else "INFO"
        
    print(f"🚀 Starting Flask API server on http://{args.host}:{args.port}")
    print(f"📊 Graph Explorer frontend should connect to this endpoint")
    
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()

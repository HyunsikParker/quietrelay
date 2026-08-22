#!/usr/bin/env python3
"""Serve the integrated QuietRelay demo on numeric loopback only."""

from __future__ import annotations

import argparse
from pathlib import Path

from quietrelay.web import DEFAULT_PORT, serve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    print(f"QuietRelay is available at http://127.0.0.1:{args.port}", flush=True)
    try:
        serve(root, port=args.port)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Leadership Intelligence — CLI entry point

Given a property address, finds the owning company and extracts
the top 15 leadership team members with LinkedIn + contact details.

Usage:
    python3 leadership_run.py --address "350 5th Ave" --city "New York" --state "NY"
    python3 leadership_run.py --address "30-02 Whitestone Expy" --city "Queens" --state "NY"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from leadership.agent import main

if __name__ == "__main__":
    main()

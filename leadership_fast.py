#!/usr/bin/env python3
"""
Leadership Intelligence — Fast Pipeline CLI

Usage:
    python3 leadership_fast.py --address "25-01 Jackson Avenue" --city "Queens" --state "NY"
    python3 leadership_fast.py --address "350 5th Ave" --city "Manhattan" --state "NY"
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from leadership.pipeline import main

if __name__ == "__main__":
    main()

"""
Run the Real Estate Stakeholder Intelligence Agent.

Usage:
  python3 run.py --address "350 5th Ave" --city "New York" --state "NY" --zip "10118"

Output:
  Printed to terminal + saved to output/results_latest.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.agent import run_agent
import argparse

def main():
    parser = argparse.ArgumentParser(
        description="Find all stakeholders for a property address",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run.py --address "350 5th Ave" --city "New York" --state "NY" --zip "10118"
  python3 run.py --address "200 Park Ave" --city "Manhattan" --state "NY"
  python3 run.py --address "123 Main St" --city "Brooklyn" --state "NY" --zip "11201"
        """
    )
    parser.add_argument("--address", required=True, help="Street address")
    parser.add_argument("--city",    required=True, help="City or borough")
    parser.add_argument("--state",   required=True, help="2-letter state code")
    parser.add_argument("--zip",     default="",    dest="zip_code", help="ZIP code (optional)")
    parser.add_argument("--quiet",   action="store_true", help="Only show final results")
    args = parser.parse_args()

    results = run_agent(
        address=args.address,
        city=args.city,
        state=args.state,
        zip_code=args.zip_code,
        verbose=not args.quiet,
    )

    if not results:
        print("\nNo stakeholders found. Check the address or try --city with the borough name.")
        sys.exit(1)

if __name__ == "__main__":
    main()

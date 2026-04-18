"""
Batch runner — processes a CSV of addresses through the agent.

Usage:
    python3 batch_run.py --input input/addresses.csv
    python3 batch_run.py --input input/addresses.csv --output results_batch.csv

Input CSV format (header row required):
    address,city,state,zip_code
    350 5th Ave,New York,NY,10118
    1 World Trade Center,New York,NY,10007

Output: combined CSV + JSON saved to output/ folder.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))


def run_agent_for_address(address: str, city: str, state: str, zip_code: str = "") -> list[dict]:
    """Run the agent synchronously for one address and return stakeholders."""
    import anthropic
    from agent.tools import TOOL_DEFINITIONS, call_tool
    from agent.prompts import SYSTEM_PROMPT
    import re

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  ✗ ANTHROPIC_API_KEY not set")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    full_address = f"{address}, {city}, {state} {zip_code}".strip()

    user_message = (
        f"Research this property and find all key stakeholders with contact details:\n\n"
        f"Address: {address}\nCity: {city}\nState: {state}\nZIP: {zip_code}\n\n"
        f"Find: Developer, Architect, GC, Owner, Lender, and Subcontractors. "
        f"For each person get phone, email, LinkedIn, and website."
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]
    tool_count = 0
    MAX_ROUNDS = 15

    for _ in range(MAX_ROUNDS):
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,  # type: ignore
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                if attempt == 2:
                    print("  ✗ Rate limit — waiting 60s")
                    time.sleep(60)
                else:
                    time.sleep(60)

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]
        messages.append({"role": "assistant", "content": response.content})

        if not tool_uses or response.stop_reason == "end_turn":
            final_text = " ".join(b.text for b in text_blocks)
            match = re.search(r"<output>\s*([\s\S]*?)\s*</output>", final_text)
            if not match:
                match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", final_text)
            stakeholders = []
            if match:
                try:
                    stakeholders = json.loads(match.group(1))
                except Exception:
                    pass
            for s in stakeholders:
                s.setdefault("property_address", full_address)
            from agent.agent import _normalize_role, _deduplicate
            for s in stakeholders:
                if "role" in s:
                    s["role"] = _normalize_role(s["role"])
            stakeholders = _deduplicate(stakeholders)
            return stakeholders

        tool_results = []
        for tool_use in tool_uses:
            tool_count += 1
            name = tool_use.name
            inputs = tool_use.input
            print(f"  [{tool_count}] {name}({json.dumps(inputs)[:60]}...)")

            import asyncio as _asyncio
            result = call_tool(name, inputs)
            result_trimmed = result if len(result) <= 2000 else result[:2000] + "...}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_trimmed,
            })

        messages.append({"role": "user", "content": tool_results})

    return []


def load_addresses_from_csv(path: str) -> list[dict]:
    addresses = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize column names (case-insensitive)
            normalized = {k.strip().lower(): v.strip() for k, v in row.items()}
            addresses.append({
                "address":  normalized.get("address", ""),
                "city":     normalized.get("city", "New York"),
                "state":    normalized.get("state", "NY"),
                "zip_code": normalized.get("zip_code", normalized.get("zip", "")),
            })
    return addresses


def save_results(all_stakeholders: list[dict], output_path: str):
    """Save combined results to CSV and JSON."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # JSON
    json_path = output_dir / output_path.replace(".csv", ".json")
    json_path.write_text(json.dumps(all_stakeholders, indent=2))

    # CSV
    csv_path = output_dir / output_path
    if all_stakeholders:
        fieldnames = list(all_stakeholders[0].keys())
        # Ensure key columns are first
        priority = ["property_address", "role", "full_name", "company", "phone", "email",
                    "linkedin_url", "website", "confidence_score", "confidence_label",
                    "sources", "permit_number", "permit_type", "notes"]
        ordered = [f for f in priority if f in fieldnames]
        ordered += [f for f in fieldnames if f not in ordered]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ordered, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_stakeholders)

    print(f"\n  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Batch run the stakeholder agent on multiple addresses")
    parser.add_argument("--input", required=True, help="Input CSV file with addresses")
    parser.add_argument("--output", default=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        help="Output CSV filename (saved in output/)")
    parser.add_argument("--delay", type=int, default=5,
                        help="Seconds to wait between addresses (default 5)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"✗ Input file not found: {args.input}")
        sys.exit(1)

    addresses = load_addresses_from_csv(args.input)
    if not addresses:
        print("✗ No addresses found in CSV")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  BATCH STAKEHOLDER AGENT")
    print(f"  {len(addresses)} addresses to process")
    print(f"  Estimated time: {len(addresses) * 2}–{len(addresses) * 3} minutes")
    print(f"{'='*60}\n")

    all_stakeholders = []
    failed = []

    for i, addr in enumerate(addresses, 1):
        full = f"{addr['address']}, {addr['city']}, {addr['state']} {addr['zip_code']}".strip()
        print(f"[{i}/{len(addresses)}] {full}")

        try:
            stakeholders = run_agent_for_address(**addr)
            count = len(stakeholders)
            all_stakeholders.extend(stakeholders)
            print(f"  ✓ Found {count} stakeholders\n")
        except Exception as e:
            print(f"  ✗ Error: {e}\n")
            failed.append(full)

        # Save progress after each address
        if all_stakeholders:
            save_results(all_stakeholders, args.output)

        # Delay between addresses to avoid rate limits
        if i < len(addresses):
            time.sleep(args.delay)

    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"  Total stakeholders: {len(all_stakeholders)}")
    print(f"  Addresses processed: {len(addresses) - len(failed)}/{len(addresses)}")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
    print(f"{'='*60}")
    save_results(all_stakeholders, args.output)


if __name__ == "__main__":
    main()

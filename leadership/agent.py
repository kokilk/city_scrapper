"""
Leadership Intelligence Agent

Given a property address → finds the owning company → extracts top 15 leaders
with LinkedIn profiles, emails, titles, and contact details.

Usage:
    from leadership.agent import run_leadership_agent
    results = run_leadership_agent("350 5th Ave", "New York", "NY")
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from leadership.tools import TOOL_DEFINITIONS, call_tool
from leadership.prompts import SYSTEM_PROMPT

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "leadership"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 40  # more rounds needed: find names → find URLs → batch scrape


# ── Output parsing ─────────────────────────────────────────────────────────────

def _parse_output(text: str) -> list[dict]:
    """Extract JSON array from <output>...</output> tags."""
    match = re.search(r"<output>\s*([\s\S]*?)\s*</output>", text)
    if not match:
        match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", text)
        if not match:
            return []
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return []


def _extract_summary(text: str) -> str:
    """Extract the 3-line summary after the output block."""
    after = re.split(r"</output>", text, maxsplit=1)
    return after[1].strip() if len(after) > 1 else ""


# ── CSV export ─────────────────────────────────────────────────────────────────

def _save_csv(leaders: list[dict], address: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]", "_", address)[:40]
    csv_path = OUTPUT_DIR / f"{slug}_{timestamp}.csv"

    fields = [
        "rank", "full_name", "title", "company",
        "email", "phone", "linkedin_url", "location",
        "about", "source", "confidence",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in leaders:
            writer.writerow({k: row.get(k, "") for k in fields})

    # Also save JSON
    json_path = OUTPUT_DIR / f"{slug}_{timestamp}.json"
    json_path.write_text(json.dumps(leaders, indent=2))

    # Always-updated "latest" copies
    latest_csv = OUTPUT_DIR / "leadership_latest.csv"
    latest_json = OUTPUT_DIR / "leadership_latest.json"
    import shutil
    shutil.copy2(csv_path, latest_csv)
    latest_json.write_text(json.dumps(leaders, indent=2))

    return csv_path


# ── Main agent loop ────────────────────────────────────────────────────────────

def run_leadership_agent(
    address: str,
    city: str,
    state: str,
    zip_code: str = "",
    verbose: bool = True,
) -> list[dict]:
    """
    Run the leadership intelligence agent for a property address.

    Returns list of leader dicts (up to 15), also saved to output/leadership/.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=api_key)

    full_address = f"{address}, {city}, {state} {zip_code}".strip().rstrip(",")
    user_message = (
        f"Find the top 15 leadership team members of the company that owns this property:\n\n"
        f"Address: {address}\n"
        f"City: {city}\n"
        f"State: {state}\n"
        f"ZIP: {zip_code}\n\n"
        f"Full address: {full_address}\n\n"
        f"Steps:\n"
        f"1. Find the company that owns this building\n"
        f"2. Find their official website and LinkedIn company page\n"
        f"3. Extract the top 15 leaders (CEO, C-suite, VPs, Directors)\n"
        f"4. Get LinkedIn profile, email, phone, and title for each person\n"
        f"5. Return structured results"
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]

    if verbose:
        print(f"\n{'='*65}")
        print(f"  LEADERSHIP INTELLIGENCE AGENT")
        print(f"  Property: {full_address}")
        print(f"  Model: {MODEL}")
        print(f"{'='*65}\n")

    tool_call_count = 0
    final_text = ""

    for round_num in range(MAX_TOOL_ROUNDS):
        # Rate limit retry
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                if attempt == 2:
                    raise
                wait = 20 * (attempt + 1)
                if verbose:
                    print(f"[agent] Rate limit — waiting {wait}s...")
                time.sleep(wait)

        tool_uses = []
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        final_text = " ".join(text_parts)
        messages.append({"role": "assistant", "content": response.content})

        if not tool_uses or response.stop_reason == "end_turn":
            if verbose:
                print(f"\n[agent] Done after {tool_call_count} tool calls")
            break

        # Execute tools
        tool_results = []
        for tool_use in tool_uses:
            tool_call_count += 1
            tool_name = tool_use.name
            tool_input = tool_use.input

            if verbose:
                args_preview = json.dumps(tool_input, separators=(",", ":"))[:120]
                print(f"[tool {tool_call_count:02d}] {tool_name}({args_preview})")

            result = call_tool(tool_name, tool_input)

            # Trim large results (Apify profiles can be big)
            if len(result) > 3000:
                result = result[:3000] + '..."}'
            result_preview = result[:200] + "..." if len(result) > 200 else result
            if verbose:
                print(f"           → {result_preview}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    else:
        if verbose:
            print(f"[agent] WARNING: Hit max tool rounds ({MAX_TOOL_ROUNDS})")

    # Parse and save
    leaders = _parse_output(final_text)
    summary = _extract_summary(final_text)

    if not leaders and verbose:
        print("[agent] WARNING: Could not parse structured output")
        print(f"[agent] Raw response:\n{final_text[:1000]}")

    csv_path = _save_csv(leaders, full_address)

    if verbose:
        print(f"\n{'='*65}")
        print(f"  RESULTS: {len(leaders)} leader(s) found")
        print()
        for ldr in leaders:
            rank = ldr.get("rank", "?")
            name = ldr.get("full_name", "?")
            title = ldr.get("title", "")
            email = ldr.get("email", "")
            linkedin = ldr.get("linkedin_url", "")
            conf = ldr.get("confidence", "")
            contacts = " | ".join(filter(None, [email, linkedin]))
            print(f"  [{rank:>2}] [{conf:<6}] {title}: {name}")
            if contacts:
                print(f"         {contacts}")
        if summary:
            print(f"\n  {summary}")
        print(f"\n  CSV  → {csv_path}")
        print(f"  JSON → {csv_path.with_suffix('.json')}")
        print(f"{'='*65}\n")

    return leaders


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Leadership Intelligence Agent")
    parser.add_argument("--address", required=True, help="Street address e.g. '350 5th Ave'")
    parser.add_argument("--city", required=True, help="City e.g. 'New York'")
    parser.add_argument("--state", required=True, help="State code e.g. 'NY'")
    parser.add_argument("--zip", default="", dest="zip_code", help="ZIP code")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    run_leadership_agent(
        address=args.address,
        city=args.city,
        state=args.state,
        zip_code=args.zip_code,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()

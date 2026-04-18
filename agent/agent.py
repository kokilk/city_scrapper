"""
Real Estate Stakeholder Intelligence Agent

Uses Claude claude-sonnet-4-6 with tool_use to autonomously research a property address
and return all key stakeholders with contact details.

Claude decides:
  - Which tools to call
  - In what order
  - How many times
  - How to interpret results

Usage:
  from agent.agent import run_agent
  results = run_agent("350 5th Ave", "New York", "NY", "10118")
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
import time
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.tools import TOOL_DEFINITIONS, call_tool
from agent.prompts import SYSTEM_PROMPT

OUTPUT_DIR = Path(__file__).parent.parent / "output"
TMP_DIR = Path(__file__).parent.parent / ".tmp"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 15  # keep under rate limit


_ROLE_ALIASES: dict[str, str] = {
    # Developer variants
    "developer / owner": "Developer",
    "developer/owner": "Developer",
    "developer (original)": "Developer",
    "developer (firm)": "Developer",
    "developer (original redeveloper)": "Developer",
    "developer (historic)": "Developer",
    "developer / co-founder": "Developer",
    "original developer": "Developer",
    "original developer / former owner": "Developer",
    "co-developer": "Developer",
    # Architect variants
    "architect of record": "Architect",
    "architect of record (original)": "Architect",
    "architect (firm)": "Architect",
    "architect (original)": "Architect",
    "architect (original — unresolved)": "Architect",
    "lead architect": "Architect",
    "aor": "Architect",
    # GC variants
    "gc": "General Contractor",
    "general contractor (original construction)": "General Contractor",
    "general contractor (original)": "General Contractor",
    "general contractor (unresolved)": "General Contractor",
    "main contractor": "General Contractor",
    # Owner variants
    "owner (entity)": "Owner",
    "owner (entity / llc)": "Owner",
    "owner entity (llc)": "Owner",
    "property owner": "Owner",
    "owner / developer (current)": "Owner",
    "owner / asset manager": "Owner",
    "owner — managing agency (commissioner)": "Owner",
    "current owner": "Owner",
    "owner (current)": "Owner",
    # Lender variants
    "lender (original)": "Lender",
    "lender (original / construction)": "Lender",
    "lender (refinance / current)": "Lender",
    "construction lender": "Lender",
    "refinance lender": "Lender",
    "co-investor / equity partner": "Lender",
    # Leasing Agent variants
    "leasing broker": "Leasing Agent",
    "leasing agent / property manager": "Leasing Agent",
    "property manager": "Leasing Agent",
    "tenant / occupant agency": "Leasing Agent",
}

_VALID_ROLES = {"Developer", "Architect", "General Contractor", "Owner", "Lender", "Subcontractor", "Leasing Agent"}


def _normalize_role(role: str) -> str:
    """Map any role variant to one of the 7 standard roles."""
    cleaned = role.strip().lower()
    if cleaned in _ROLE_ALIASES:
        return _ROLE_ALIASES[cleaned]
    # Check if it already matches a valid role (case-insensitive)
    for valid in _VALID_ROLES:
        if cleaned == valid.lower():
            return valid
    # Fuzzy fallback: if valid role string appears anywhere in the label
    for valid in _VALID_ROLES:
        if valid.lower() in cleaned:
            return valid
    return role  # return as-is if we can't map it


def _deduplicate(stakeholders: list[dict]) -> list[dict]:
    """
    Merge duplicate stakeholders:
    - Same individual: same full_name (fuzzy) regardless of role
    - Same company: same company name + same role, no individual named
    """
    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""

    seen_names: dict[str, int] = {}   # normalized_name -> index in result
    seen_entities: dict[str, int] = {}  # normalized_company+role -> index in result
    result: list[dict] = []

    for s in stakeholders:
        name = _norm(s.get("full_name", ""))
        company = _norm(s.get("company", ""))
        role = s.get("role", "")

        if name and len(name) > 3:
            if name in seen_names:
                # Merge: fill in missing fields from this duplicate
                existing = result[seen_names[name]]
                for field in ("phone", "email", "linkedin_url", "website", "linkedin_headline"):
                    if not existing.get(field) and s.get(field):
                        existing[field] = s[field]
                # Keep higher confidence score
                if s.get("confidence_score", 0) > existing.get("confidence_score", 0):
                    existing["confidence_score"] = s["confidence_score"]
                    existing["confidence_label"] = s["confidence_label"]
                continue
            seen_names[name] = len(result)
            result.append(s)
        elif company:
            entity_key = company + _norm(role)
            if entity_key in seen_entities:
                existing = result[seen_entities[entity_key]]
                for field in ("phone", "email", "website"):
                    if not existing.get(field) and s.get(field):
                        existing[field] = s[field]
                continue
            seen_entities[entity_key] = len(result)
            result.append(s)
        else:
            result.append(s)

    return result


def _parse_output(text: str) -> list[dict]:
    """Extract JSON array from <output>...</output> tags in Claude's response."""
    match = re.search(r"<output>\s*([\s\S]*?)\s*</output>", text)
    if not match:
        # Try to find a bare JSON array
        match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", text)
        if not match:
            return []
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return []


def _save_results(
    stakeholders: list[dict],
    address: str,
    city: str,
    state: str,
    zip_code: str,
) -> Path:
    """Save results to output/ directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Add property_address to every row if missing
    full_address = f"{address}, {city}, {state} {zip_code}".strip()
    for s in stakeholders:
        s.setdefault("property_address", full_address)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]", "_", full_address)[:40]

    # Timestamped file
    out_path = OUTPUT_DIR / f"{slug}_{timestamp}.json"
    out_path.write_text(json.dumps(stakeholders, indent=2))

    # Latest file (n8n reads this)
    latest = OUTPUT_DIR / "results_latest.json"
    latest.write_text(json.dumps(stakeholders, indent=2))

    return latest


def run_agent(
    address: str,
    city: str,
    state: str,
    zip_code: str = "",
    verbose: bool = True,
) -> list[dict]:
    """
    Run the stakeholder intelligence agent for a property address.

    Returns list of stakeholder dicts, also saved to output/results_latest.json.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=api_key)

    full_address = f"{address}, {city}, {state} {zip_code}".strip().rstrip(",")
    user_message = (
        f"Research this property and find all key stakeholders with contact details:\n\n"
        f"Address: {address}\n"
        f"City: {city}\n"
        f"State: {state}\n"
        f"ZIP: {zip_code}\n\n"
        f"Full address: {full_address}\n\n"
        f"Find: Developer, Architect, GC, Owner, Lender, and any Subcontractors. "
        f"For each person get their phone, email, LinkedIn, and website."
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]

    if verbose:
        print(f"\n{'='*60}")
        print(f"  STAKEHOLDER INTELLIGENCE AGENT")
        print(f"  Property: {full_address}")
        print(f"  Model: {MODEL}")
        print(f"{'='*60}\n")

    tool_call_count = 0
    final_text = ""

    # ── Agentic loop ──────────────────────────────────────────────────────────
    for round_num in range(MAX_TOOL_ROUNDS):
        # Retry on rate limit with backoff
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
                wait = 60 * (attempt + 1)
                if verbose:
                    print(f"[agent] Rate limit hit — waiting {wait}s before retry...")
                time.sleep(wait)

        # Collect text and tool use blocks
        tool_uses = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        final_text = " ".join(text_parts)

        # Add assistant message to history
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls → Claude is done
        if not tool_uses or response.stop_reason == "end_turn":
            if verbose:
                print(f"\n[agent] Done after {tool_call_count} tool calls")
            break

        # Execute all tool calls and collect results
        tool_results = []
        for tool_use in tool_uses:
            tool_call_count += 1
            tool_name = tool_use.name
            tool_input = tool_use.input

            if verbose:
                print(f"[tool {tool_call_count}] {tool_name}({json.dumps(tool_input, separators=(',',':'))})")

            result = call_tool(tool_name, tool_input)

            # Trim large results to stay under token limits
            result_trimmed = result if len(result) <= 2000 else result[:2000] + "...}"
            result_preview = result[:200] + "..." if len(result) > 200 else result
            if verbose:
                print(f"         → {result_preview}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_trimmed,
            })

        # Feed results back to Claude
        messages.append({"role": "user", "content": tool_results})

    else:
        if verbose:
            print(f"[agent] WARNING: Hit max tool rounds ({MAX_TOOL_ROUNDS})")

    # ── Parse output ─────────────────────────────────────────────────────────
    stakeholders = _parse_output(final_text)

    if not stakeholders and verbose:
        print("[agent] WARNING: Could not parse structured output from Claude")
        print(f"[agent] Raw response:\n{final_text[:1000]}")

    # Normalize roles and deduplicate
    for s in stakeholders:
        if "role" in s:
            s["role"] = _normalize_role(s["role"])
    stakeholders = _deduplicate(stakeholders)

    if verbose:
        print(f"[agent] After dedup: {len(stakeholders)} stakeholders")

    # Save to output/
    latest_path = _save_results(stakeholders, address, city, state, zip_code)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  RESULTS: {len(stakeholders)} stakeholder(s) found")
        for s in stakeholders:
            label = s.get("confidence_label", "?")
            role = s.get("role", "?")
            name = s.get("full_name") or s.get("company", "?")
            email = s.get("email", "")
            linkedin = s.get("linkedin_url", "")
            contacts = " | ".join(filter(None, [email, linkedin]))
            print(f"  [{label}] {role}: {name}" + (f" — {contacts}" if contacts else ""))
        print(f"\n  Output → {latest_path}")
        print(f"{'='*60}\n")

    return stakeholders


def main() -> None:
    """CLI entry point — called by run.py."""
    import argparse
    parser = argparse.ArgumentParser(description="Real Estate Stakeholder Intelligence Agent")
    parser.add_argument("--address", required=True, help="Street address e.g. '350 5th Ave'")
    parser.add_argument("--city", required=True, help="City e.g. 'New York'")
    parser.add_argument("--state", required=True, help="State code e.g. 'NY'")
    parser.add_argument("--zip", default="", dest="zip_code", help="ZIP code")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    run_agent(
        address=args.address,
        city=args.city,
        state=args.state,
        zip_code=args.zip_code,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()

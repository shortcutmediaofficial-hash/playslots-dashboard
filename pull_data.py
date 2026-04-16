#!/usr/bin/env python3
"""
Rep Performance Metrics — Data Fetcher
Pulls conversation data from Intercom API (and optionally GHL API),
calculates first response times, resolution times, and SLA breaches,
then writes a JSON file consumed by the dashboard.

Usage:
    python pull_data.py

Configure your API keys below or set them as environment variables:
    INTERCOM_TOKEN
    GHL_API_KEY
    GHL_LOCATION_ID
"""

import os
import json
import time
import datetime
import requests
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
INTERCOM_TOKEN = os.getenv(
    "INTERCOM_TOKEN",
    ""
)
GHL_API_KEY = os.getenv(
    "GHL_API_KEY",
    ""
)
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")

# SLA thresholds (seconds)
SLA_FIRST_RESPONSE = 3 * 60   # 3 minutes
SLA_RESOLUTION     = 10 * 60  # 10 minutes

# Only track these reps (case-insensitive partial match)
# Includes both Intercom names (full) and GHL names (abbreviated)
TRACKED_REPS = ["O PSM", "C PSM", "AM PSM", "Hernando PSM", "OP", "CP", "AP", "HP"]

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "dashboard_data.json")

# ── Intercom helpers ───────────────────────────────────────────────────────
INTERCOM_BASE = "https://api.intercom.io"

def intercom_headers():
    return {
        "Authorization": f"Bearer {INTERCOM_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def fetch_intercom_conversations(days_back=30):
    """Fetch recent conversations from Intercom using the Search API."""
    conversations = []
    cutoff = int(time.time()) - (days_back * 86400)

    # Use the search endpoint to get conversations created after cutoff
    url = f"{INTERCOM_BASE}/conversations/search"
    payload = {
        "query": {
            "operator": "AND",
            "value": [
                {
                    "field": "created_at",
                    "operator": ">",
                    "value": cutoff
                },
                {
                    "field": "source.type",
                    "operator": "=",
                    "value": "conversation"
                }
            ]
        },
        "pagination": {"per_page": 150}
    }

    page = 1
    while True:
        print(f"  Fetching Intercom conversations page {page}...")
        resp = requests.post(url, headers=intercom_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for conv in data.get("conversations", []):
            conversations.append(conv)

        # Pagination
        pagination = data.get("pages", {})
        next_cursor = pagination.get("next", {})
        if next_cursor and next_cursor.get("starting_after"):
            payload["pagination"]["starting_after"] = next_cursor["starting_after"]
            page += 1
        else:
            break

    print(f"  → Fetched {len(conversations)} Intercom conversations")
    return conversations


def fetch_intercom_conversation_parts(conversation_id):
    """Fetch full conversation parts (messages) for a conversation."""
    url = f"{INTERCOM_BASE}/conversations/{conversation_id}"
    resp = requests.get(url, headers=intercom_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def process_intercom_data(conversations):
    """Process raw Intercom conversations into metrics."""
    records = []

    for i, conv in enumerate(conversations):
        conv_id = conv.get("id", "")
        created_at = conv.get("created_at", 0)

        # Determine if player-initiated (source.delivered_as == "customer_initiated")
        source = conv.get("source", {})
        initiated_by = source.get("delivered_as", "")
        author_type = source.get("author", {}).get("type", "")
        is_player_initiated = author_type in ("user", "lead", "contact")

        # Get assignee info
        assignee = conv.get("assignee", {}) or {}
        rep_name = assignee.get("name", "Unassigned")
        rep_id = assignee.get("id", "")

        # State and timing
        state = conv.get("state", "open")
        updated_at = conv.get("updated_at", created_at)

        # Get first response time from statistics if available
        stats = conv.get("statistics", {}) or {}
        first_response_time = stats.get("first_contact_reply_at")
        time_to_first_response = None
        if first_response_time and created_at:
            time_to_first_response = first_response_time - created_at

        # Resolution time
        time_to_close = None
        if state == "closed" and stats.get("last_close_at"):
            time_to_close = stats["last_close_at"] - created_at
        elif state == "closed":
            time_to_close = updated_at - created_at

        # SLA calculations
        first_response_breach = False
        resolution_breach = False
        if is_player_initiated and time_to_first_response is not None:
            first_response_breach = time_to_first_response > SLA_FIRST_RESPONSE
        if time_to_close is not None:
            resolution_breach = time_to_close > SLA_RESOLUTION

        # Tags
        tags = [t.get("name", "") for t in conv.get("tags", {}).get("tags", [])]

        # Contact info
        contacts = conv.get("contacts", {}).get("contacts", [])
        player_name = contacts[0].get("name", "Unknown") if contacts else "Unknown"
        player_id = contacts[0].get("id", "") if contacts else ""

        records.append({
            "id": conv_id,
            "source": "intercom",
            "created_at": created_at,
            "created_date": datetime.datetime.fromtimestamp(created_at).strftime("%Y-%m-%d") if created_at else "",
            "created_hour": datetime.datetime.fromtimestamp(created_at).hour if created_at else 0,
            "player_name": player_name,
            "player_id": player_id,
            "player_initiated": is_player_initiated,
            "rep_name": rep_name,
            "rep_id": str(rep_id),
            "state": state,
            "first_response_seconds": time_to_first_response,
            "resolution_seconds": time_to_close,
            "first_response_breach": first_response_breach,
            "resolution_breach": resolution_breach,
            "tags": tags,
        })

    return records


# ── GHL (GoHighLevel) helpers ─────────────────────────────────────────────

GHL_BASE = "https://services.leadconnectorhq.com"

def ghl_headers():
    return {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Version": "2021-07-28",
        "Accept": "application/json",
    }

def fetch_ghl_conversations(days_back=30):
    """Fetch recent conversations from GoHighLevel."""
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        print("  ⚠ GHL API key or Location ID not configured — skipping GHL data.")
        return []

    conversations = []
    url = f"{GHL_BASE}/conversations/search"
    params = {
        "locationId": GHL_LOCATION_ID,
        "limit": 100,
    }

    print(f"  Fetching GHL conversations...")
    try:
        resp = requests.get(url, headers=ghl_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        conversations = data.get("conversations", [])
        print(f"  → Fetched {len(conversations)} GHL conversations")
    except Exception as e:
        print(f"  ⚠ GHL fetch error: {e}")

    return conversations


def process_ghl_data(conversations):
    """Process raw GHL conversations into metrics."""
    records = []
    cutoff = time.time() - (30 * 86400)

    for conv in conversations:
        created_str = conv.get("dateAdded", "")
        # Parse ISO date
        try:
            created_dt = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            created_at = int(created_dt.timestamp())
        except:
            continue

        if created_at < cutoff:
            continue

        conv_id = conv.get("id", "")
        contact_name = conv.get("contactName", "Unknown")
        contact_id = conv.get("contactId", "")
        assigned_to = conv.get("assignedTo", "Unassigned")
        status = conv.get("status", "open")

        # GHL doesn't provide first response times natively —
        # we'd need to fetch individual messages. For now, track what's available.
        last_message_date = conv.get("lastMessageDate", "")

        records.append({
            "id": conv_id,
            "source": "ghl",
            "created_at": created_at,
            "created_date": datetime.datetime.fromtimestamp(created_at).strftime("%Y-%m-%d"),
            "created_hour": datetime.datetime.fromtimestamp(created_at).hour,
            "player_name": contact_name,
            "player_id": contact_id,
            "player_initiated": True,  # Assume inbound
            "rep_name": assigned_to,
            "rep_id": assigned_to,
            "state": "closed" if status == "completed" else "open",
            "first_response_seconds": None,
            "resolution_seconds": None,
            "first_response_breach": None,
            "resolution_breach": None,
            "tags": [],
        })

    return records


# ── Aggregation ────────────────────────────────────────────────────────────

def compute_summary(records):
    """Compute dashboard summary metrics."""
    now = time.time()

    total = len(records)
    player_initiated = [r for r in records if r["player_initiated"]]

    # First response stats (player-initiated only, with data)
    fr_records = [r for r in player_initiated if r["first_response_seconds"] is not None]
    fr_times = [r["first_response_seconds"] for r in fr_records]
    fr_breaches = [r for r in fr_records if r["first_response_breach"]]

    # Resolution stats (closed conversations with data)
    res_records = [r for r in records if r["resolution_seconds"] is not None]
    res_times = [r["resolution_seconds"] for r in res_records]
    res_breaches = [r for r in res_records if r["resolution_breach"]]

    # Per-rep breakdown
    rep_stats = defaultdict(lambda: {
        "total": 0, "closed": 0,
        "fr_times": [], "res_times": [],
        "fr_breaches": 0, "res_breaches": 0,
    })

    for r in records:
        rep = r["rep_name"]
        rep_stats[rep]["total"] += 1
        if r["state"] == "closed":
            rep_stats[rep]["closed"] += 1
        if r["first_response_seconds"] is not None:
            rep_stats[rep]["fr_times"].append(r["first_response_seconds"])
            if r["first_response_breach"]:
                rep_stats[rep]["fr_breaches"] += 1
        if r["resolution_seconds"] is not None:
            rep_stats[rep]["res_times"].append(r["resolution_seconds"])
            if r["resolution_breach"]:
                rep_stats[rep]["res_breaches"] += 1

    rep_summary = []
    for name, s in rep_stats.items():
        avg_fr = (sum(s["fr_times"]) / len(s["fr_times"])) if s["fr_times"] else None
        avg_res = (sum(s["res_times"]) / len(s["res_times"])) if s["res_times"] else None
        median_fr = sorted(s["fr_times"])[len(s["fr_times"])//2] if s["fr_times"] else None
        median_res = sorted(s["res_times"])[len(s["res_times"])//2] if s["res_times"] else None

        rep_summary.append({
            "name": name,
            "total_conversations": s["total"],
            "closed": s["closed"],
            "avg_first_response_seconds": round(avg_fr, 1) if avg_fr else None,
            "median_first_response_seconds": round(median_fr, 1) if median_fr else None,
            "avg_resolution_seconds": round(avg_res, 1) if avg_res else None,
            "median_resolution_seconds": round(median_res, 1) if median_res else None,
            "fr_breaches": s["fr_breaches"],
            "res_breaches": s["res_breaches"],
            "fr_breach_rate": round(s["fr_breaches"] / len(s["fr_times"]) * 100, 1) if s["fr_times"] else 0,
            "res_breach_rate": round(s["res_breaches"] / len(s["res_times"]) * 100, 1) if s["res_times"] else 0,
        })

    # Daily volume
    daily = defaultdict(lambda: {"total": 0, "breaches": 0, "closed": 0})
    for r in records:
        d = r["created_date"]
        daily[d]["total"] += 1
        if r["first_response_breach"]:
            daily[d]["breaches"] += 1
        if r["state"] == "closed":
            daily[d]["closed"] += 1

    daily_summary = [{"date": d, **v} for d, v in sorted(daily.items())]

    # Hourly heatmap
    hourly = defaultdict(int)
    for r in records:
        hourly[r["created_hour"]] += 1
    hourly_summary = [{"hour": h, "count": hourly.get(h, 0)} for h in range(24)]

    return {
        "generated_at": datetime.datetime.now().isoformat(),
        "tracked_reps": TRACKED_REPS,
        "sla": {
            "first_response_seconds": SLA_FIRST_RESPONSE,
            "resolution_seconds": SLA_RESOLUTION,
        },
        "overview": {
            "total_conversations": total,
            "player_initiated": len(player_initiated),
            "avg_first_response": round(sum(fr_times) / len(fr_times), 1) if fr_times else None,
            "median_first_response": round(sorted(fr_times)[len(fr_times)//2], 1) if fr_times else None,
            "avg_resolution": round(sum(res_times) / len(res_times), 1) if res_times else None,
            "median_resolution": round(sorted(res_times)[len(res_times)//2], 1) if res_times else None,
            "fr_breach_count": len(fr_breaches),
            "fr_breach_rate": round(len(fr_breaches) / len(fr_records) * 100, 1) if fr_records else 0,
            "res_breach_count": len(res_breaches),
            "res_breach_rate": round(len(res_breaches) / len(res_records) * 100, 1) if res_records else 0,
        },
        "reps": sorted(rep_summary, key=lambda x: x["total_conversations"], reverse=True),
        "daily": daily_summary,
        "hourly": hourly_summary,
        "conversations": records,
    }


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Rep Performance Metrics — Data Fetcher")
    print("=" * 60)

    all_records = []

    # 1. Intercom
    if INTERCOM_TOKEN:
        print("\n📡 Fetching Intercom data...")
        try:
            convos = fetch_intercom_conversations(days_back=30)
            records = process_intercom_data(convos)
            all_records.extend(records)
            print(f"  ✓ Processed {len(records)} Intercom records")
        except Exception as e:
            print(f"  ✗ Intercom error: {e}")
    else:
        print("\n⚠ No Intercom token configured.")

    # 2. GHL
    print("\n📡 Fetching GoHighLevel data...")
    try:
        ghl_convos = fetch_ghl_conversations(days_back=30)
        ghl_records = process_ghl_data(ghl_convos)
        all_records.extend(ghl_records)
        if ghl_records:
            print(f"  ✓ Processed {len(ghl_records)} GHL records")
    except Exception as e:
        print(f"  ✗ GHL error: {e}")

    # 3. Filter to tracked reps only
    if TRACKED_REPS:
        tracked_lower = [name.lower() for name in TRACKED_REPS]
        before = len(all_records)
        all_records = [
            r for r in all_records
            if any(t in r["rep_name"].lower() for t in tracked_lower)
        ]
        print(f"\n🎯 Filtered to tracked reps: {', '.join(TRACKED_REPS)}")
        print(f"   {before} → {len(all_records)} conversations")

    # 4. Compute summary
    print("\n📊 Computing metrics...")
    summary = compute_summary(all_records)

    # 4. Write output
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n✅ Dashboard data written to: {OUTPUT_FILE}")
    print(f"   Open dashboard.html in your browser to view results.\n")


if __name__ == "__main__":
    main()

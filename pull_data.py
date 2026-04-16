"""
Rep Performance Metrics — Data Fetcher (GHL-focused)
Pulls conversation data from GoHighLevel API,
calculates metrics, and writes a JSON file consumed by the dashboard.
"""

import os
import json
import time
import datetime
import requests
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")

# SLA thresholds (seconds)
SLA_FIRST_RESPONSE = 3 * 60   # 3 minutes
SLA_RESOLUTION     = 10 * 60  # 10 minutes

# Track these reps
TRACKED_REPS = ["O PSM", "C PSM", "AM PSM", "Hernando PSM", "OP", "CP", "AP", "HP"]

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "dashboard_data.json")

# ── GHL helpers ─────────────────────────────────────────────────────────

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
        print("  ⚠ Missing GHL_API_KEY or GHL_LOCATION_ID")
        return []

    url = f"{GHL_BASE}/conversations/"
    params = {
        "locationId": GHL_LOCATION_ID,
        "limit": 100,
    }

    try:
        print(f"  Fetching GHL conversations...")
        resp = requests.get(url, headers=ghl_headers(), params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            convos = data.get("conversations", [])
            print(f"  → Fetched {len(convos)} GHL conversations")
            return convos
        else:
            print(f"  ✗ GHL API error: {resp.status_code}")
            return []
    except Exception as e:
        print(f"  ✗ GHL fetch error: {e}")
        return []

def process_ghl_data(convos):
    """Process GHL conversation data."""
    records = []
    
    for conv in convos:
        conv_id = conv.get("id", "")
        created_at = conv.get("dateAdded", 0)
        if isinstance(created_at, str):
            try:
                created_at = int(datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp())
            except:
                created_at = int(time.time())
        
        status = conv.get("status", "").lower()
        assigned_to = conv.get("assignedTo", {})
        if isinstance(assigned_to, dict):
            assigned_to = assigned_to.get("name", "Unassigned")
        else:
            assigned_to = str(assigned_to) if assigned_to else "Unassigned"
        
        contact_name = conv.get("contactName", "Unknown")
        contact_id = conv.get("contactId", "")
        
        records.append({
            "id": conv_id,
            "source": "ghl",
            "created_at": created_at,
            "created_date": datetime.datetime.fromtimestamp(created_at).strftime("%Y-%m-%d") if created_at else "",
            "created_hour": datetime.datetime.fromtimestamp(created_at).hour if created_at else 0,
            "player_name": contact_name,
            "player_id": contact_id,
            "player_initiated": True,
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

def compute_summary(records):
    """Compute dashboard summary metrics."""
    total = len(records)
    player_initiated = [r for r in records if r["player_initiated"]]
    
    # Per-rep breakdown
    rep_stats = defaultdict(lambda: {"total": 0, "closed": 0})
    
    for r in records:
        rep = r["rep_name"]
        rep_stats[rep]["total"] += 1
        if r["state"] == "closed":
            rep_stats[rep]["closed"] += 1
    
    rep_summary = []
    for name, s in rep_stats.items():
        rep_summary.append({
            "name": name,
            "total_conversations": s["total"],
            "closed": s["closed"],
            "avg_first_response_seconds": None,
            "median_first_response_seconds": None,
            "avg_resolution_seconds": None,
            "median_resolution_seconds": None,
            "fr_breaches": 0,
            "res_breaches": 0,
            "fr_breach_rate": 0,
            "res_breach_rate": 0,
        })
    
    # Daily breakdown
    daily_stats = defaultdict(lambda: {"total": 0, "breaches": 0})
    for r in records:
        day = r["created_date"]
        daily_stats[day]["total"] += 1
    
    daily_summary = []
    for day in sorted(daily_stats.keys()):
        s = daily_stats[day]
        daily_summary.append({
            "date": day,
            "total_conversations": s["total"],
            "sla_breaches": s["breaches"],
        })
    
    # Hourly breakdown
    hourly_stats = defaultdict(int)
    for r in records:
        hour = r["created_hour"]
        hourly_stats[hour] += 1
    
    hourly_summary = []
    for hour in range(24):
        hourly_summary.append({
            "hour": f"{hour:02d}:00",
            "conversations": hourly_stats.get(hour, 0),
        })
    
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
            "avg_first_response": None,
            "median_first_response": None,
            "avg_resolution": None,
            "median_resolution": None,
            "fr_breach_count": 0,
            "fr_breach_rate": 0,
            "res_breach_count": 0,
            "res_breach_rate": 0,
        },
        "reps": sorted(rep_summary, key=lambda x: x["total_conversations"], reverse=True),
        "daily": daily_summary,
        "hourly": hourly_summary,
        "conversations": records,
    }

def main():
    print("=" * 60)
    print("  Rep Performance Metrics — Data Fetcher (GHL)")
    print("=" * 60)
    
    all_records = []
    
    # Fetch GHL data
    print("\n📡 Fetching GoHighLevel data...")
    try:
        ghl_convos = fetch_ghl_conversations(days_back=30)
        ghl_records = process_ghl_data(ghl_convos)
        all_records.extend(ghl_records)
        if ghl_records:
            print(f"  ✓ Processed {len(ghl_records)} GHL records")
        else:
            print(f"  ⚠ No GHL conversations found")
    except Exception as e:
        print(f"  ✗ GHL error: {e}")
    
    # Filter to tracked reps only (if configured)
    if TRACKED_REPS and all_records:
        tracked_lower = [name.lower() for name in TRACKED_REPS]
        before = len(all_records)
        all_records = [
            r for r in all_records
            if any(t in r["rep_name"].lower() for t in tracked_lower)
        ]
        print(f"\n🎯 Filtered to tracked reps: {', '.join(TRACKED_REPS)}")
        print(f"   {before} → {len(all_records)} conversations")
    
    # Compute summary
    print("\n📊 Computing metrics...")
    summary = compute_summary(all_records)
    
    # Write output
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n✅ Dashboard data written to: {OUTPUT_FILE}")
    print(f"   Open dashboard.html in your browser to view results.\n")

if __name__ == "__main__":
    main()

# PlaySlots Rep Performance Dashboard

Live support metrics for: **C PSM · AM PSM · O PSM · Hernando PSM**

SLA: 3 min first response · 10 min resolution

---

## Quick Start

### 1. Pull live data
```bash
pip install requests
python pull_data.py
```

### 2a. Open locally (just you)
Open `dashboard.html` in your browser.

### 2b. Share with your team (local network)
```bash
npm install
node server.js
```
Then share `http://YOUR-IP:3000` with your team.

### 2c. Deploy to the cloud (anyone, anywhere)

**Render.com (free):**
1. Push this folder to a GitHub repo
2. render.com → New Web Service → connect repo
3. Build command: `npm install`
4. Start command: `node server.js`
5. Share the Render URL

**Railway.app (free):**
1. Push to GitHub
2. railway.app → New Project → Deploy from GitHub
3. Add env vars, deploy, share URL

---

## Files

| File | Purpose |
|------|---------|
| `dashboard.html` | Interactive dashboard UI |
| `pull_data.py` | Fetches Intercom + GHL data |
| `server.js` | Web server for team sharing |
| `preview.html` | Demo with sample data (no API needed) |
| `package.json` | Node.js dependencies |

---

## Change SLA or Reps

Edit the top of `pull_data.py`:
```python
SLA_FIRST_RESPONSE = 3 * 60    # seconds
SLA_RESOLUTION     = 10 * 60   # seconds
TRACKED_REPS = ["C PSM", "AM PSM", "O PSM", "Hernando PSM"]
```

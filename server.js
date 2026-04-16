/**
 * Rep Performance Dashboard — Web Server
 *
 * A lightweight Express server that:
 *  1. Serves the dashboard HTML
 *  2. Provides a /api/data endpoint that reads the latest dashboard_data.json
 *  3. Provides a /api/refresh endpoint to trigger a fresh data pull
 *
 * Usage:
 *   npm install express
 *   node server.js
 *
 * Then share http://YOUR_IP:3000 with your team.
 * For public access, deploy to Render, Railway, or any Node host.
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const app = express();
const PORT = process.env.PORT || 3000;
const DATA_FILE = path.join(__dirname, 'dashboard_data.json');
const PULL_SCRIPT = path.join(__dirname, 'pull_data.py');

// Serve static files (dashboard.html, etc.)
app.use(express.static(__dirname));

// API: Get latest dashboard data
app.get('/api/data', (req, res) => {
  try {
    if (!fs.existsSync(DATA_FILE)) {
      return res.status(404).json({ error: 'No data yet. Run pull_data.py or hit /api/refresh.' });
    }
    const raw = fs.readFileSync(DATA_FILE, 'utf8');
    const data = JSON.parse(raw);
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// API: Trigger a fresh data pull
app.post('/api/refresh', (req, res) => {
  try {
    console.log('[refresh] Running pull_data.py...');
    const output = execSync(`python3 "${PULL_SCRIPT}"`, {
      cwd: __dirname,
      timeout: 120000,
      encoding: 'utf8',
    });
    console.log(output);
    res.json({ success: true, output });
  } catch (e) {
    console.error('[refresh] Error:', e.message);
    res.status(500).json({ error: e.message });
  }
});

// Fallback: serve dashboard.html for root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'dashboard.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n  Rep Performance Dashboard`);
  console.log(`  Running at http://localhost:${PORT}`);
  console.log(`  Share with your team: http://YOUR_LOCAL_IP:${PORT}\n`);
});

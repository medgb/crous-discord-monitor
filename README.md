# CROUS Discord Room Availability Monitor 🏠🚨

A lightweight, production-grade Python monitoring service that continuously watches a specific **CROUS "Trouver un logement"** search and immediately notifies you via **Discord Webhook** when a new room or accommodation becomes available.

Each notification delivers all essential details (residence name, address, room type, surface area, rent in €/month) along with a **direct clickable CROUS booking URL**, enabling you to immediately open the offer on your phone and apply manually before spots run out.

---

## Key Features

- **⚡ Instant Notification Latency**: Detects newly available rooms within 30–60 seconds.
- **📱 Phone Push Notifications**: Mentions your Discord User ID (`<@USER_ID>`) so Discord pushes a high-priority alert directly to your phone.
- **🔄 State Transition Engine**: Detects newly listed rooms and reappeared rooms (`unavailable -> available`), while gracefully ignoring disappeared rooms without false alerts.
- **🛡️ Zero-Spam Startup**: Automatically records existing search results as baseline on first launch without spamming your Discord channel.
- **💾 SQLite Persistence**: Maintains state across restarts in a lightweight, single-file SQLite database.
- **🌐 Reverse-Engineered Direct API**: Queries the CROUS SvelteKit backend directly (`POST /api/fr/search/{tool_id}`) with automatic multi-page pagination and coordinate normalization.
- **🛡️ Fault Tolerance**: Network errors and CROUS server blips never corrupt local state or trigger false alerts; exponential backoff retries transient failures seamlessly.
- **🐳 24/7 VPS Deployment**: Ready-to-use Docker and `docker-compose.yml` with auto-restart (`restart: unless-stopped`).

---

## Architecture & Project Structure

```
crous-discord-monitor/
├── src/
│   ├── main.py                  # CLI entrypoint (--once, --test-notification, continuous)
│   ├── config.py                # Environment loading, validation & secret masking
│   ├── logging_config.py        # Structured logging with sensitive data redaction
│   ├── monitor.py               # Polling loop & state synchronization engine
│   ├── crous/
│   │   ├── models.py            # Normalized Accommodation & SearchQuery models
│   │   ├── parser.py            # Search URL parser & API response transformer
│   │   ├── client.py            # HTTP client with pagination, retry & backoff
│   │   └── auth.py              # Persistent session manager & login helper
│   ├── storage/
│   │   └── database.py          # SQLite persistence & transition detector
│   └── notifier/
│       └── discord.py           # Discord Webhook sender & rich embed builder
├── tests/
│   ├── conftest.py              # Test fixtures and mock responses
│   ├── test_parser.py           # URL & response parsing unit tests
│   ├── test_database.py         # SQLite transition logic unit tests
│   ├── test_monitor.py          # Monitor lifecycle & resilience tests
│   ├── test_discord.py          # Webhook embed & ping tests
│   └── test_integration.py      # Live CROUS API integration test
├── data/                        # Persistent SQLite database (gitignored)
├── Dockerfile                   # Production container definition
├── docker-compose.yml           # Continuous deployment configuration
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment variables
└── README.md
```

---

## 1. Quickstart & Local Setup (Windows / Linux / macOS)

### Step 1: Clone or Navigate to the Project
```bash
git clone https://github.com/medgb/crous-discord-monitor.git
cd crous-discord-monitor
```

### Step 2: Create and Activate Virtual Environment
```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```
```bash
# Linux / macOS
cp .env.example .env
```

Open `.env` and fill in your values:
```env
# 1. Monitored CROUS Search URL (Copy from your browser when filtering Trouver un Logement)
CROUS_SEARCH_URL=https://trouverunlogement.lescrous.fr/tools/42/search?bounds=4.9452443_45.2443315_6.2866978_45.8679317

# 2. Discord Webhook URL (Server Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN

# 3. Optional: Your Discord User ID for mobile notifications (Right-click your name in Discord -> Copy User ID)
DISCORD_USER_ID=123456789012345678

# Polling Interval (in seconds, default: 30)
POLL_INTERVAL_SECONDS=30

# Log Level: INFO or DEBUG
LOG_LEVEL=INFO
```

---

## 2. CLI Modes & Verification

### A. Test Discord Notification
Verify that your webhook and phone push notification are working:
```bash
python -m src.main --test-notification
```
*You will immediately receive a test embed message in your Discord channel.*

### B. Run a Single CROUS Check (`--once`)
Fetch live results for your configured `CROUS_SEARCH_URL`, print all detected accommodations in your console, update the local SQLite database, and exit without looping:
```bash
python -m src.main --once
```

### C. Start Continuous Monitoring (Production Mode)
Start the continuous monitoring loop:
```bash
python -m src.main
```
*On first startup, all existing offers are recorded as baseline. Whenever a new room appears, a Discord notification is dispatched immediately.*

---

## 3. Continuous 24/7 VPS Deployment (Docker)

To keep monitoring active continuously even when your personal computer is turned off, deploy the monitor on a cloud VPS (e.g. Hetzner, OVH, DigitalOcean, AWS, GCP, Scaleway) with Docker.

### Step 1: Copy Project to your VPS
```bash
scp -r . user@your-vps-ip:/opt/crous-monitor
ssh user@your-vps-ip
cd /opt/crous-monitor
```

### Step 2: Configure `.env` on VPS
```bash
cp .env.example .env
nano .env   # Enter your CROUS_SEARCH_URL and DISCORD_WEBHOOK_URL
```

### Step 3: Start with Docker Compose
```bash
docker compose up -d --build
```

### Step 4: Manage & View Logs
```bash
# View live streaming logs
docker compose logs -f

# Check container status
docker compose ps

# Stop monitor
docker compose down

# Restart monitor
docker compose restart
```
The container is configured with `restart: unless-stopped` to automatically resume monitoring if the VPS reboots.

---

## 4. How Search URLs Work

You can configure any search URL from [trouverunlogement.lescrous.fr](https://trouverunlogement.lescrous.fr/):

1. Open `https://trouverunlogement.lescrous.fr/` in your browser.
2. Select the year (e.g. *2025–2026* or *2026–2027*).
3. Search for your target city (e.g. *Grenoble*, *Paris*, *Lyon*, *Lille*, *Corte*).
4. Apply any desired filters (Max Price, Min Area, Room Type, PMR Accessibility).
5. Copy the full URL from your browser address bar into `CROUS_SEARCH_URL` in `.env`.

Supported parameters in the URL:
- `tools/42/search` or `tools/47/search` (academic year tool ID)
- `bounds=lon1_lat1_lon2_lat2` (geographic bounding box)
- `maxPrice=500` (maximum rent)
- `minArea=18` (minimum surface)
- `occupationModes=alone` (single occupancy)
- `accessibility=prm` (PMR accessible)

---

## 5. Running Automated Tests

Run the full test suite with `pytest`:
```bash
pytest -v
```

Test coverage includes:
- **`test_parser.py`**: Search URL parameter parsing, coordinate normalization, precision calculations, item parsing into data models.
- **`test_database.py`**: Baseline recording, new room detection, disappearance detection, reappearance alert transitions, duplicate handling, ordering immunity, restart persistence.
- **`test_monitor.py`**: Polling cycle orchestration, baseline protection, network failure resilience without state degradation.
- **`test_discord.py`**: Embed generation, user mention formatting, small batch individual embeds, large batch digest grouping.
- **`test_integration.py`**: End-to-end integration test against live CROUS search endpoint.

---

## 6. Security & Best Practices

- **Never Commit Secrets**: `.env`, SQLite databases (`data/`), and session state files are strictly excluded via `.gitignore`.
- **Log Masking**: Webhook tokens and passwords are automatically redacted from all log outputs.
- **Polite Polling**: Default polling interval is set to 30 seconds. Do not set sub-second intervals to ensure reliable long-term monitoring.
- **Manual Application**: This service only detects availability and alerts you. The user manually opens the direct CROUS link and completes the application on their own.

---

## License
MIT License.

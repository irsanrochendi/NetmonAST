# NetMon AST — Network Monitoring System

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-PostgreSQL-orange.svg)](https://timescale.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Network Monitoring untuk Mikrotik, ESXi, dan VM Guest.**

Fitur:
- 📡 **SNMP Polling** — CPU, memory, uptime, interface traffic (Mikrotik)
- 🖥️ **ESXi Monitoring** — CPU, memory, datastore, VM list via pyVmomi
- 📊 **VM Guest Agent** — Linux (systemd) + Windows (PyInstaller .exe) via psutil
- 🔔 **Alert System** — Threshold-based alerts via Telegram + Email
- 📈 **Dashboard** — React + Tailwind + Recharts real-time
- 📄 **Export** — PDF/Excel reports untuk laporan bulanan
- 🔒 **Security** — JWT auth, credential encryption, rate limiting
- 🔧 **Maintenance Window** — Bungkam alert saat perawatan terjadwal
- 👥 **Role-based Access** — Admin vs Viewer

## Quick Start

```bash
# Clone
git clone git@github.com:irsanrochendi/NetmonAST.git
cd NetmonAST

# Setup environment
cp .env.example .env
# Edit .env dengan credential yang sesuai

# Generate secret key
openssl rand -hex 32

# Run with Docker Compose
docker compose up -d --build

# Access
# API Docs : http://localhost:8000/docs
# Dashboard: http://localhost:3000
# Default   : admin / admin123
```

## Dokumentasi

- [Panduan Instalasi](docs/INSTALLATION.md) — Setup lengkap, SNMP Mikrotik, ESXi, troubleshooting
- [API Docs](http://localhost:8000/docs) — Swagger UI (setelah running)

## Arsitektur

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│  Mikrotik   │◄──►│  SNMP Poller │───►│               │
└─────────────┘    └──────────────┘    │               │
                                       │  TimescaleDB  │
┌─────────────┐    ┌──────────────┐    │  (PostgreSQL) │
│    ESXi     │◄──►│ ESXi Poller  │───►│               │
└─────────────┘    └──────────────┘    │               │
                                       └───────┬───────┘
┌─────────────┐    ┌──────────────┐            │
│  VM Guest   │───►│  API Server  │◄───────────┘
│   (agent)   │    │  (FastAPI)   │
└─────────────┘    └──────┬───────┘
                          │
                   ┌──────▼───────┐
                   │   Dashboard   │
                   │ (React+TW)    │
                   └──────────────┘
```

## Struktur Project

```
NetmonAST/
├── backend/              # FastAPI + poller workers
│   ├── app/
│   │   ├── api/routes/   # REST endpoints
│   │   ├── collectors/   # SNMP + ESXi clients
│   │   ├── workers/      # snmp_poller, esxi_poller, alert_worker
│   │   ├── services/     # alert_engine, export, maintenance
│   │   ├── auth.py       # JWT authentication
│   │   ├── security.py   # Encryption, rate limiting, validation
│   │   ├── models.py     # SQLAlchemy ORM
│   │   └── config.py     # Settings
│   ├── alembic/          # Database migrations
│   └── requirements.txt
├── frontend/             # React + Tailwind dashboard
│   └── src/
│       ├── pages/        # Login, Overview, Devices, Alerts, Settings
│       ├── components/   # Sidebar, Layout, UI components
│       ├── services/     # Axios API client
│       └── contexts/     # Auth context
├── agents/               # VM guest agents
│   ├── linux/            # systemd service
│   └── windows/          # Windows Service + PyInstaller
├── docs/                 # Dokumentasi instalasi
├── scripts/              # health_check.sh, backup_db.sh
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

MIT

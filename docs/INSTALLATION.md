# NetMon — Panduan Instalasi

## Daftar Isi
1. [Prasyarat](#prasyarat)
2. [Clone & Setup](#clone--setup)
3. [Konfigurasi .env](#konfigurasi-env)
4. [Generate Secret Key](#generate-secret-key)
5. [Jalankan dengan Docker Compose](#jalankan-dengan-docker-compose)
6. [Setup SNMP di Mikrotik](#setup-snmp-di-mikrotik)
7. [Setup ESXi](#setup-esxi)
8. [Akses Dashboard](#akses-dashboard)
9. [Deploy Agent VM](#deploy-agent-vm)
10. [Troubleshooting](#troubleshooting)

---

## Prasyarat

| Komponen | Minimum |
|----------|---------|
| Docker Engine | 24.x+ |
| Docker Compose | 2.x+ |
| RAM | 4 GB |
| Disk | 20 GB free |
| OS | Linux / Windows (WSL2) / macOS |

---

## Clone & Setup

```bash
# Clone repository
git clone https://github.com/irsanrochendi/netmon.git
cd netmon

# Copy environment template
cp .env.example .env
```

---

## Konfigurasi .env

Edit file `.env` dengan nilai yang sesuai:

```env
# ── Database ───────────────────────────────────────────────────────
DB_USER=netmon
DB_PASSWORD=your_strong_password_here    # Ganti!
DB_NAME=netmon
DB_PORT=5432

# ── API ────────────────────────────────────────────────────────────
API_PORT=8000
SECRET_KEY=                            # Generate dengan cara di bawah

# ── Poller Intervals (detik) ───────────────────────────────────────
SNMP_POLL_INTERVAL=60
ESXI_POLL_INTERVAL=120

# ── Telegram (opsional) ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_CHAT_ID=-1001234567890

# ── Email SMTP (opsional) ──────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_FROM_EMAIL=netmon@yourdomain.com
```

### Generate Secret Key

```bash
# Linux/macOS
openssl rand -hex 32

# PowerShell (Windows)
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
```

Paste hasilnya ke `SECRET_KEY` di `.env`.

---

## Jalankan dengan Docker Compose

```bash
# Build dan start semua container
docker compose up -d --build

# Cek status
docker compose ps

# Lihat logs
docker compose logs -f api
docker compose logs -f snmp-poller
docker compose logs -f esxi-poller
docker compose logs -f alert-worker

# Stop semua
docker compose down

# Stop + hapus volume (⚠️ hapus semua data)
docker compose down -v
```

### Struktur Container

| Container | Port | Fungsi |
|-----------|------|--------|
| `netmon-db` | 5432 | TimescaleDB |
| `netmon-api` | 8000 | FastAPI REST API |
| `netmon-snmp-poller` | — | Polling Mikrotik via SNMP |
| `netmon-esxi-poller` | — | Polling ESXi via pyVmomi |
| `netmon-alert-worker` | — | Evaluasi alert + notifikasi |

---

## Setup SNMP di Mikrotik

### Via Winbox / Webfig

1. **IP → SNMP**
2. Centang **Enabled**
3. **Community**: Buat community baru (default: `public`)
   - Name: `netmon`
   - Address: `0.0.0.0/0` (atau IP server NetMon)
4. **Apply**

### Via Terminal Mikrotik

```routeros
# Enable SNMP
/snmp set enabled=yes

# Buat community (ganti 'netmon_read' dengan nama yang diinginkan)
/snmp community set [find name="public"] name=netmon_read addresses=0.0.0.0/0 read-access=yes write-access=no

# Opsional: set contact dan location
/snmp set contact="netmon@local" location="Server Room"
```

### Verifikasi SNMP dari Server NetMon

```bash
# Install snmp tools (jika belum)
apt install snmp  # Debian/Ubuntu

# Test query
snmpget -v2c -c netmon_read <IP_MIKROTIK> 1.3.6.1.2.1.1.1.0
```

---

## Setup ESXi

### Enable SSH di ESXi

1. vSphere Client → Host → Actions → Services → Enable SSH
2. Atau: Host → Manage → Services → TSM-SSH → Start

### Buat Read-Only User (opsional, recommended)

```bash
# SSH ke ESXi
ssh root@<IP_ESXI>

# Buat user read-only
esxcli system account add -d="NetMon Monitor" -i=netmon -p="<password>" -c="<password>"

# Assign role (ReadOnly)
esxcli system permission set -i=netmon -r=ReadOnly
```

### Verifikasi dari Server NetMon

```bash
# Test pyVmomi connection
python3 -c "
from pyVim.connect import SmartConnect
import ssl
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
si = SmartConnect(host='<IP_ESXI>', user='netmon', pwd='<password>', sslContext=ctx)
print('Connected:', si.content.about.fullName)
"
```

---

## Akses Dashboard

Setelah `docker compose up -d`:

| URL | Deskripsi |
|-----|-----------|
| `http://localhost:8000/docs` | Swagger API docs |
| `http://localhost:8000/redoc` | ReDoc API docs |
| `http://localhost:3000` | Dashboard (jika frontend di-build) |

**Default login:**
- Username: `admin`
- Password: `admin123`
- ⚠️ **Ganti password pertama kali!**

---

## Deploy Agent VM

### Linux (systemd)

```bash
# Di VM Linux:
curl -fsSL http://<NETMON_SERVER>:8000/agents/linux/install.sh | \
  sudo bash -s -- \
  --server http://<NETMON_SERVER>:8000 \
  --token <AGENT_TOKEN>
```

### Windows (PowerShell Admin)

```powershell
# Di VM Windows:
.\install_service.ps1 -ServerUrl "http://<NETMON_SERVER>:8000" -AgentToken "<AGENT_TOKEN>"
```

### Register VM Baru

```bash
# Via API
curl -X POST http://<NETMON_SERVER>:8000/api/agent/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Web Server 01", "location": "Rack A3"}'

# Via script
python agents/register_vm.py --name "Web Server 01" --server http://<NETMON_SERVER>:8000
```

---

## Troubleshooting

### Container tidak start

```bash
# Cek logs
docker compose logs <container_name>

# Cek health
docker inspect netmon-db | grep -A5 Health
```

### SNMP poll gagal

```bash
# Test dari dalam container
docker exec -it netmon-snmp-poller python3 -c "
from app.collectors.snmp_client import SNMPClient
c = SNMPClient(host='<IP_MIKROTIK>', community='netmon_read')
r = c.poll()
print('Success:', r.success)
print('Error:', r.error)
"
```

### ESXi poll gagal

```bash
# Test dari dalam container
docker exec -it netmon-esxi-poller python3 -c "
from app.collectors.esxi_client import ESXiClient
c = ESXiClient(host='<IP_ESXI>', username='netmon', password='<password>')
r = c.poll()
print('Success:', r.success)
print('Error:', r.error)
"
```

### Database connection error

```bash
# Cek DB running
docker compose ps timescaledb

# Test connection
docker exec -it netmon-db psql -U netmon -d netmon -c "SELECT 1"
```

### Reset password admin

```bash
docker exec -it netmon-api python3 -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models import AdminUser
from app.auth import hash_password
from sqlalchemy.future import select

async def reset():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == 'admin'))
        user = result.scalar_one()
        user.password_hash = hash_password('admin123')
        await db.commit()
        print('Password reset to admin123')

asyncio.run(reset())
"
```

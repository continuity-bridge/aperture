---
author: Jerry Jackson (Uncle Tallest)
copyright: © 2026 Jerry Jackson. All rights reserved.
version: v0.3.1
---
# Aperture

**Local filesystem access for claude.ai browser users.**

The Claude Desktop app can read and write your local files through MCP filesystem tools. If you use claude.ai in a browser tab, you don't get those tools by default.

Aperture fixes that. It runs a local bridge on your computer and exposes it to claude.ai via a secure public tunnel -- no Desktop app required.

---

## How It Works

```
claude.ai (browser) → HTTPS → Serveo tunnel → Aperture MCP server → Your filesystem
```

Three components run on your machine:

- **`aperture.py`** -- HTTP bridge on localhost:8765, handles filesystem operations
- **`aperture-mcp-server.py`** -- MCP SSE server on localhost:10000, translates MCP protocol to bridge calls
- **Serveo tunnel** -- SSH-based tunnel, gives claude.ai a public HTTPS URL to reach your machine

Claude gets seven filesystem tools: `read_file`, `write_file`, `list_directory`, `create_directory`, `move_file`, `get_file_info`, `list_allowed_directories`.

**Security:** localhost-only bridge, session tokens, explicit directory allowlist. You control exactly what Claude can access.

---

## Installation

### Quick install (recommended)

```bash
bash install-aperture.sh
```

The installer handles everything: dependency checks, Python packages, directory setup, subdomain configuration, and optional systemd autostart. Takes 2-3 minutes.

### Manual install

**Requirements:** Python 3.10+, pip, SSH client

```bash
# Install Python dependencies
pip install flask flask-cors mcp httpx starlette uvicorn --break-system-packages

# Start the bridge
python3 aperture.py start --allow ~/Documents/claude-work

# In another terminal, start the MCP server
python3 aperture-mcp-server.py --port 10000

# In another terminal, start the tunnel
ssh -R aperture-myname-myhostname:80:localhost:10000 serveo.net
```

---

## Usage

After install, `aperture-start.sh` manages everything:

```bash
# Start (reads config from ~/.aperture.conf)
aperture-start.sh

# Check status and get current connector URL
aperture-start.sh --status

# Stop all processes
aperture-start.sh --stop

# Start with specific directories
aperture-start.sh --allow ~/Documents --allow ~/Projects
```

On startup, Aperture prints the connector URL to paste into claude.ai:

```
┌─────────────────────────────────────────────────────┐
│  Aperture is running                                │
├─────────────────────────────────────────────────────┤
│  Connector URL (paste into claude.ai):              │
│  https://aperture-yourname-yourhostname.serveo.net/sse
└─────────────────────────────────────────────────────┘
```

**Register in claude.ai:** Settings → Connectors → + → Custom MCP Server → paste URL.

---

## Configuration

Config lives at `~/.aperture.conf` (created by installer):

```bash
SUBDOMAIN="aperture-yourname-yourhostname"
ALLOW_DIRS=(
  "/home/yourname/Documents"
  "/home/yourname/Projects"
)
```

Edit this file to change allowed directories or subdomain, then restart Aperture.

---

## Security

- Bridge binds to `127.0.0.1` only -- not accessible from your network
- Session tokens are 32-byte cryptographically random values, 24-hour expiry
- All filesystem operations validated against the allowlist before execution
- Serveo tunnel is outbound SSH only -- no inbound ports opened on your machine
- CORS restricted to `claude.ai` and `localhost` origins

---

## Troubleshooting

**Connector URL not connecting:**
```bash
aperture-start.sh --status
curl http://localhost:10000/health
```

**Invalid token errors:**
Token is regenerated each time the bridge starts. If the MCP server has a stale token, restart everything with `aperture-start.sh`.

**Serveo subdomain taken:**
Edit `~/.aperture.conf` and change `SUBDOMAIN` to something unique, then restart.

**Port already in use:**
```bash
aperture-start.sh --stop
aperture-start.sh
```

**Logs:**
```bash
~/.aperture-logs/bridge.log
~/.aperture-logs/mcp.log
~/.aperture-logs/tunnel.log
```

---

## Integration with Continuity Bridge

Aperture is a tool in the [Continuity Bridge](https://github.com/continuity-bridge/continuity-bridge) ecosystem. If you're using Continuity Bridge, Aperture gives web instances the same filesystem access that Desktop app instances have natively.

Install path in Continuity Bridge: `Tools/aperture/`

---

## Platform Support

| Platform | Status |
|----------|--------|
| Linux | Supported |
| macOS | Should work, untested |
| Windows | Not yet supported |
| Android | Not applicable |

---

## License

Same license as Continuity Bridge. See LICENSE in the main repository.

---

## Credits

**Architecture & implementation:** Uncle Tallest (Jerry Jackson) & Vector (Claude instances)  
**Part of:** [Continuity Bridge](https://github.com/continuity-bridge/continuity-bridge)

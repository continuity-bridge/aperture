---
author: Jerry Jackson (Uncle Tallest)
copyright: © 2026 Jerry Jackson. All rights reserved.
version: v0.3.0
---
# Aperture MCP Server Setup

**Automated filesystem access for claude.ai through proper MCP protocol.**

## What This Does

Wraps the Aperture HTTP bridge as a proper MCP server, making filesystem tools available to:
- claude.ai (browser or Desktop)
- Any MCP client
- Future Anthropic products

**Architecture:**
```
Claude Backend → MCP Protocol → aperture-mcp-server.py → HTTP → Aperture Bridge → Your Filesystem
```

---

## Installation

### 1. Install MCP SDK

```bash
pip install mcp --break-system-packages
```

### 2. Make Server Executable

```bash
chmod +x /home/tallest/Substrate/aperture-mcp-server.py
```

### 3. Get Aperture Session Token

Start Aperture bridge if not already running:
```bash
cd ~/.claude/scripts/aperture
python3 tam-bridge.py start --allow /home/tallest/Substrate
```

The bridge will output a session token. Save it:
```bash
# Copy the token from bridge startup output, then:
echo "YOUR_SESSION_TOKEN_HERE" > ~/.aperture-token
chmod 600 ~/.aperture-token
```

---

## Configuration

### For claude.ai (Desktop App)

Add to Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "aperture": {
      "command": "python3",
      "args": ["/home/tallest/Substrate/aperture-mcp-server.py"],
      "env": {
        "APERTURE_BRIDGE_URL": "http://localhost:8765",
        "APERTURE_TOKEN_FILE": "/home/tallest/.aperture-token"
      }
    }
  }
}
```

### For claude.ai (Browser via Settings)

*(This requires browser-based MCP support, which may not be available yet)*

If/when claude.ai supports MCP servers in browser:
1. Go to Settings → Integrations
2. Add MCP Server
3. Point to `aperture-mcp-server.py`
4. Configure environment variables

---

## Usage

Once configured, Claude will automatically have these tools available:

- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `list_directory(path)` - List directory contents
- `create_directory(path)` - Create directory
- `move_file(source, destination)` - Move/rename file
- `get_file_info(path)` - Get file metadata
- `list_allowed_directories()` - Show accessible directories

**Example (in Claude conversation):**
```
You: "Create a file at /home/tallest/Substrate/test.md with 'Hello World'"
Claude: [calls write_file tool automatically]
Claude: "Created file successfully"
```

---

## Testing

### Test from command line:

```bash
# Start Aperture bridge if not running
cd ~/.claude/scripts/aperture
python3 tam-bridge.py start --allow /home/tallest/Substrate

# In another terminal, test MCP server:
python3 /home/tallest/Substrate/aperture-mcp-server.py
# (Should start without errors - Ctrl+C to stop)
```

### Test from Claude Desktop:

1. Restart Claude Desktop (to load new MCP server config)
2. In conversation: "List the allowed directories"
3. Claude should call `list_allowed_directories()` and show results

---

## Troubleshooting

**"No Aperture session token found"**
→ Create `~/.aperture-token` with token from bridge startup

**"Failed to connect to Aperture bridge"**
→ Make sure `tam-bridge.py` is running on localhost:8765

**"MCP SDK not installed"**
→ Run `pip install mcp --break-system-packages`

**Tools not showing up in Claude**
→ Restart Claude Desktop after config changes

---

## Security Notes

- Token stored in `~/.aperture-token` (chmod 600)
- Only accessible from localhost
- Directory allowlist enforced by bridge
- Same security model as Desktop app's native filesystem MCP

---

## What This Achieves

**For Tam (browser user):**
- Can use Aperture bridge via manual browser console (existing method)
- Will eventually work automatically when browser MCP support lands

**For You (Desktop user):**
- Aperture bridge now accessible as proper MCP server
- Works alongside Desktop's native filesystem MCP
- Can use same bridge from Desktop or browser

**For DevRel Portfolio:**
- Shows understanding of MCP architecture
- Demonstrates bridge building between systems
- Production-ready MCP server implementation
- Addresses real user need (browser filesystem access)

---

**Created:** March 13, 2026  
**Author:** Uncle Tallest (Jerry)  
**Part of:** Continuity Bridge ecosystem

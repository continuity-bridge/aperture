#!/usr/bin/env python3
# Author: Jerry Jackson (Uncle Tallest)
# Copyright: © 2026 Jerry Jackson. All rights reserved.
# Version: v0.3.1
"""
Aperture MCP Server (SSE transport)
=====================================

MCP server exposing Aperture filesystem bridge via SSE transport.
Tailscale Funnel handles TLS -- this serves plain HTTP on localhost.

Architecture:
  claude.ai → HTTPS → Tailscale Funnel → HTTP:8765 → This server → Filesystem

Usage:
  python3 aperture-mcp-server.py [--port 8765] [--allow /path/to/dir]

Registration:
  In claude.ai Settings → Connectors → Add custom:
  URL: https://persephone.fell-pentatonic.ts.net/sse
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    from mcp import types
except ImportError:
    print("Error: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import Response
    import uvicorn
except ImportError:
    print("Error: starlette/uvicorn not installed.", file=sys.stderr)
    print("Run: pip install starlette uvicorn --break-system-packages", file=sys.stderr)
    sys.exit(1)

# Configuration
BRIDGE_URL = os.getenv("APERTURE_BRIDGE_URL", "http://localhost:8765")
TOKEN_FILE = Path(os.getenv("APERTURE_TOKEN_FILE", "~/.aperture-token")).expanduser()
ALLOWED_DIRS = []


def get_session_token() -> str:
    token = os.getenv("APERTURE_SESSION_TOKEN")
    if token:
        return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    raise RuntimeError(
        f"No Aperture session token found. "
        f"Set APERTURE_SESSION_TOKEN or create {TOKEN_FILE}"
    )


async def call_bridge(tool: str, params: dict) -> dict:
    token = get_session_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BRIDGE_URL}/mcp/{tool}",
                json=params,
                headers={
                    "Content-Type": "application/json",
                    "X-MCP-Token": token
                }
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                raise RuntimeError(data.get("error", "Unknown error from Aperture"))
            return data
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Aperture HTTP error {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to connect to Aperture bridge at {BRIDGE_URL}: {e}")


server = Server("aperture")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="read_file",
            description="Read contents of a file from local filesystem via Aperture",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to file"}},
                "required": ["path"]
            }
        ),
        types.Tool(
            name="write_file",
            description="Write content to a file on local filesystem via Aperture",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to file"},
                    "content": {"type": "string", "description": "Content to write"}
                },
                "required": ["path", "content"]
            }
        ),
        types.Tool(
            name="list_directory",
            description="List contents of a directory via Aperture",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to directory"}},
                "required": ["path"]
            }
        ),
        types.Tool(
            name="create_directory",
            description="Create a directory via Aperture",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path"}},
                "required": ["path"]
            }
        ),
        types.Tool(
            name="move_file",
            description="Move or rename a file via Aperture",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"}
                },
                "required": ["source", "destination"]
            }
        ),
        types.Tool(
            name="get_file_info",
            description="Get metadata about a file via Aperture",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        ),
        types.Tool(
            name="list_allowed_directories",
            description="List directories that Aperture has permission to access",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[types.TextContent]:
    try:
        result = await call_bridge(name, arguments or {})

        if name == "read_file":
            return [types.TextContent(type="text", text=result.get("content", ""))]

        elif name == "write_file":
            return [types.TextContent(
                type="text",
                text=f"Wrote {result.get('bytes_written', 0)} bytes to {arguments['path']}"
            )]

        elif name == "list_directory":
            entries = result.get("entries", [])
            lines = "\n".join(
                f"{'[DIR]' if e.get('is_directory') else '[FILE]'} {e.get('name')}"
                for e in entries
            )
            return [types.TextContent(type="text", text=lines or "(empty)")]

        elif name == "list_allowed_directories":
            dirs = result.get("allowed_directories", [])
            return [types.TextContent(
                type="text",
                text="Allowed directories:\n" + "\n".join(f"  {d}" for d in dirs)
            )]

        elif name == "create_directory":
            return [types.TextContent(type="text", text=f"Created: {result.get('path')}")]

        elif name == "move_file":
            return [types.TextContent(
                type="text",
                text=f"Moved {arguments['source']} -> {arguments['destination']}"
            )]

        elif name == "get_file_info":
            info = result.get("info", {})
            return [types.TextContent(
                type="text",
                text="\n".join(f"{k}: {v}" for k, v in info.items())
            )]

        else:
            return [types.TextContent(type="text", text=str(result))]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def make_app(port: int):
    sse = SseServerTransport("/messages")

    async def handle_sse(scope, receive, send):
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(
                streams[0], streams[1],
                server.create_initialization_options()
            )

    async def handle_messages(scope, receive, send):
        await sse.handle_post_message(scope, receive, send)

    async def health(scope, receive, send):
        from starlette.responses import PlainTextResponse
        response = PlainTextResponse("aperture-mcp ok")
        await response(scope, receive, send)

    async def app(scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope["method"]
            if path == "/sse" and method == "GET":
                await handle_sse(scope, receive, send)
            elif path == "/messages" and method == "POST":
                await handle_messages(scope, receive, send)
            elif path == "/health":
                await health(scope, receive, send)
            else:
                from starlette.responses import Response
                response = Response("Not Found", status_code=404)
                await response(scope, receive, send)

    return app


def main():
    parser = argparse.ArgumentParser(description="Aperture MCP Server (SSE)")
    parser.add_argument("--port", type=int, default=8766,
                        help="Port to listen on (default: 8766, separate from bridge on 8765)")
    parser.add_argument("--allow", action="append", default=[],
                        help="Allowed directory (informational, enforced by bridge)")
    args = parser.parse_args()

    print(f"Aperture MCP Server (SSE transport)")
    print(f"Listening on: http://localhost:{args.port}")
    print(f"Bridge URL:   {BRIDGE_URL}")
    print(f"")
    print(f"Register in claude.ai Settings -> Connectors:")
    print(f"  https://persephone.fell-pentatonic.ts.net/sse")
    print(f"  (requires: tailscale funnel {args.port})")
    print(f"")
    print(f"Health check: http://localhost:{args.port}/health")

    app = make_app(args.port)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

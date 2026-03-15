#!/usr/bin/env python3
# Author: Jerry Jackson (Uncle Tallest)
# Copyright: © 2026 Jerry Jackson. All rights reserved.
# Version: v0.3.0
"""
aperture.py - Local MCP Filesystem Bridge for Browser Users

Enables claude.ai browser tabs to access local filesystem by running
a localhost HTTP server that exposes filesystem tools to the Aperture
MCP server layer.

Author: Uncle Tallest (Jerry Jackson)
Purpose: Extend MCP filesystem access to browser-only claude.ai users
Security: localhost-only, explicit directory allowlist, session tokens

Usage:
    python3 aperture.py start --allow ~/Documents/claude-work
    python3 aperture.py stop
    python3 aperture.py status
"""

import sys
import os
import json
import secrets
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class MCPFilesystemBridge:
    """
    Local filesystem MCP server for browser clients.
    
    Replicates the Desktop app's filesystem tools via HTTP API.
    """
    
    def __init__(self, allowed_dirs: List[str], port: int = 8765):
        self.allowed_dirs = [Path(d).expanduser().resolve() for d in allowed_dirs]
        self.port = port
        self.session_token = secrets.token_urlsafe(32)
        self.token_created = datetime.now()
        self.token_lifetime = timedelta(hours=24)
        
        # Create Flask app
        self.app = Flask(__name__)
        
        # CORS - only allow claude.ai
        CORS(self.app, origins=[
            "https://claude.ai",
            "https://*.claude.ai",
            "http://localhost:*",  # For development
        ])
        
        # Register routes
        self._register_routes()
        
        logger.info(f"MCP Bridge initialized")
        logger.info(f"Allowed directories: {self.allowed_dirs}")
        logger.info(f"Session token: {self.session_token}")
    
    def _register_routes(self):
        """Register HTTP endpoints for MCP tools."""
        
        @self.app.route('/status', methods=['GET'])
        def status():
            """Health check endpoint."""
            return jsonify({
                "status": "running",
                "allowed_dirs": [str(d) for d in self.allowed_dirs],
                "uptime": str(datetime.now() - self.token_created),
                "version": "0.1.0"
            })
        
        @self.app.route('/auth', methods=['POST'])
        def auth():
            """
            Authenticate and get session token.
            
            Browser extension calls this first to get token.
            """
            # In production, this would validate user somehow
            # For MVP, just return the token (localhost-only anyway)
            return jsonify({
                "token": self.session_token,
                "expires": (self.token_created + self.token_lifetime).isoformat(),
                "allowed_dirs": [str(d) for d in self.allowed_dirs]
            })
        
        @self.app.route('/mcp/read_file', methods=['POST'])
        def read_file():
            """Read file contents (MCP Filesystem:read_file equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            path = self._validate_path(data.get('path'))
            
            if not path:
                abort(403, "Path not in allowed directories")
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return jsonify({
                    "success": True,
                    "content": content,
                    "path": str(path)
                })
            except Exception as e:
                logger.error(f"Error reading {path}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
        
        @self.app.route('/mcp/write_file', methods=['POST'])
        def write_file():
            """Write file contents (MCP Filesystem:write_file equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            path = self._validate_path(data.get('path'))
            content = data.get('content', '')
            
            if not path:
                abort(403, "Path not in allowed directories")
            
            try:
                # Ensure parent directory exists
                path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return jsonify({
                    "success": True,
                    "path": str(path),
                    "bytes_written": len(content)
                })
            except Exception as e:
                logger.error(f"Error writing {path}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
        
        @self.app.route('/mcp/list_directory', methods=['POST'])
        def list_directory():
            """List directory contents (MCP Filesystem:list_directory equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            path = self._validate_path(data.get('path'))
            
            if not path:
                abort(403, "Path not in allowed directories")
            
            try:
                if not path.is_dir():
                    abort(400, f"{path} is not a directory")
                
                entries = []
                for item in sorted(path.iterdir()):
                    entries.append({
                        "name": item.name,
                        "type": "DIR" if item.is_dir() else "FILE",
                        "path": str(item)
                    })
                
                return jsonify({
                    "success": True,
                    "path": str(path),
                    "entries": entries
                })
            except Exception as e:
                logger.error(f"Error listing {path}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
        
        @self.app.route('/mcp/list_allowed_directories', methods=['GET', 'POST'])
        def list_allowed_directories():
            """List allowed directories (MCP Filesystem:list_allowed_directories)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            return jsonify({
                "success": True,
                "allowed_directories": [str(d) for d in self.allowed_dirs]
            })
        
        @self.app.route('/mcp/create_directory', methods=['POST'])
        def create_directory():
            """Create directory (MCP Filesystem:create_directory equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            path = self._validate_path(data.get('path'))
            
            if not path:
                abort(403, "Path not in allowed directories")
            
            try:
                path.mkdir(parents=True, exist_ok=True)
                
                return jsonify({
                    "success": True,
                    "path": str(path)
                })
            except Exception as e:
                logger.error(f"Error creating {path}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
        
        @self.app.route('/mcp/move_file', methods=['POST'])
        def move_file():
            """Move/rename file (MCP Filesystem:move_file equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            source = self._validate_path(data.get('source'))
            destination = self._validate_path(data.get('destination'))
            
            if not source or not destination:
                abort(403, "Paths must be in allowed directories")
            
            try:
                source.rename(destination)
                
                return jsonify({
                    "success": True,
                    "source": str(source),
                    "destination": str(destination)
                })
            except Exception as e:
                logger.error(f"Error moving {source} to {destination}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
        
        @self.app.route('/mcp/get_file_info', methods=['POST'])
        def get_file_info():
            """Get file metadata (MCP Filesystem:get_file_info equivalent)."""
            if not self._validate_token():
                abort(401, "Invalid or missing token")
            
            data = request.json
            path = self._validate_path(data.get('path'))
            
            if not path:
                abort(403, "Path not in allowed directories")
            
            try:
                stat = path.stat()
                
                return jsonify({
                    "success": True,
                    "path": str(path),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "is_dir": path.is_dir(),
                    "is_file": path.is_file()
                })
            except Exception as e:
                logger.error(f"Error getting info for {path}: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500
    
    def _validate_token(self) -> bool:
        """Validate session token from request."""
        token = request.headers.get('X-MCP-Token')
        
        if not token:
            # Also check JSON body for convenience
            if request.json:
                token = request.json.get('token')
        
        if not token:
            logger.warning(f"Missing token from {request.remote_addr}")
            return False
        
        if token != self.session_token:
            logger.warning(f"Invalid token from {request.remote_addr}")
            return False
        
        # Check token age
        if datetime.now() - self.token_created > self.token_lifetime:
            logger.warning("Token expired")
            return False
        
        return True
    
    def _validate_path(self, path_str: Optional[str]) -> Optional[Path]:
        """
        Validate that path is within allowed directories.
        
        Returns resolved Path if valid, None if invalid.
        """
        if not path_str:
            return None
        
        try:
            path = Path(path_str).expanduser().resolve()
            
            # Check if path is within any allowed directory
            for allowed in self.allowed_dirs:
                try:
                    path.relative_to(allowed)
                    return path
                except ValueError:
                    continue
            
            logger.warning(f"Path {path} not in allowed directories")
            return None
            
        except Exception as e:
            logger.error(f"Error validating path {path_str}: {e}")
            return None
    
    def run(self):
        """Start the MCP bridge server."""
        logger.info(f"Starting MCP Bridge on http://localhost:{self.port}")
        logger.info(f"Browser extension should connect to this URL")
        logger.info(f"Session token: {self.session_token}")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        
        self.app.run(
            host='127.0.0.1',  # localhost only (security)
            port=self.port,
            debug=False
        )


def save_pid(pid: int):
    """Save PID file for daemon management."""
    pid_file = Path.home() / '.aperture-bridge.pid'
    pid_file.write_text(str(pid))
    logger.info(f"PID {pid} saved to {pid_file}")


def load_pid() -> Optional[int]:
    """Load PID from file."""
    pid_file = Path.home() / '.aperture-bridge.pid'
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except:
            return None
    return None


def is_running(pid: int) -> bool:
    """Check if process is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Aperture Bridge - Local MCP Filesystem for claude.ai browser users"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start the bridge')
    start_parser.add_argument(
        '--allow',
        action='append',
        required=True,
        help='Allowed directory (can specify multiple)'
    )
    start_parser.add_argument(
        '--port',
        type=int,
        default=8765,
        help='Port to listen on (default: 8765)'
    )
    
    # Stop command
    subparsers.add_parser('stop', help='Stop the bridge')
    
    # Status command
    subparsers.add_parser('status', help='Check bridge status')
    
    args = parser.parse_args()
    
    if args.command == 'start':
        # Check if already running
        pid = load_pid()
        if pid and is_running(pid):
            print(f"Bridge already running (PID {pid})")
            sys.exit(1)
        
        # Start bridge
        bridge = MCPFilesystemBridge(
            allowed_dirs=args.allow,
            port=args.port
        )
        
        # Save PID
        save_pid(os.getpid())
        
        try:
            bridge.run()
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
            pid_file = Path.home() / '.tam-bridge.pid'
            if pid_file.exists():
                pid_file.unlink()
    
    elif args.command == 'stop':
        pid = load_pid()
        if not pid or not is_running(pid):
            print("Bridge not running")
            sys.exit(1)
        
        try:
            os.kill(pid, 15)  # SIGTERM
            print(f"Stopped bridge (PID {pid})")
            
            pid_file = Path.home() / '.aperture-bridge.pid'
            if pid_file.exists():
                pid_file.unlink()
        except Exception as e:
            print(f"Error stopping bridge: {e}")
            sys.exit(1)
    
    elif args.command == 'status':
        pid = load_pid()
        if not pid:
            print("Bridge not running (no PID file)")
            sys.exit(0)
        
        if is_running(pid):
            print(f"Bridge running (PID {pid})")
            print("Aperture bridge running on http://localhost:8765")
        else:
            print(f"Bridge not running (stale PID {pid})")
            pid_file = Path.home() / '.aperture-bridge.pid'
            if pid_file.exists():
                pid_file.unlink()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

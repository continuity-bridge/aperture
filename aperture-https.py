#!/usr/bin/env python3
# Author: Jerry Jackson (Uncle Tallest)
# Copyright: © 2026 Jerry Jackson. All rights reserved.
# Version: v0.3.1
"""
aperture-https.py - HTTPS Wrapper for Aperture MCP Bridge

DEPRECATED: This approach (self-signed certs) is superseded by using
Tailscale Funnel or Serveo tunnel, which provide real TLS termination
without self-signed certificate warnings.

Kept for reference and for local network setups that may need it.
For standard installation, use aperture-start.sh instead.
"""
# NOTE: This file is retained for reference only.
# Use aperture-start.sh for standard installation.

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import argparse

# Import the existing aperture bridge
try:
    from aperture import MCPFilesystemBridge, save_pid, load_pid, is_running
except ImportError:
    print("Error: aperture.py not found in same directory")
    print("Make sure aperture.py is in the same location as this script")
    sys.exit(1)


def generate_self_signed_cert(cert_dir: Path):
    """
    Generate self-signed SSL certificate for localhost.
    
    Uses openssl to create:
    - localhost.key (private key)
    - localhost.crt (self-signed certificate)
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    
    key_file = cert_dir / "localhost.key"
    cert_file = cert_dir / "localhost.crt"
    
    # Check if already exists
    if key_file.exists() and cert_file.exists():
        print(f"✓ Certificates already exist:")
        print(f"  Key:  {key_file}")
        print(f"  Cert: {cert_file}")
        return key_file, cert_file
    
    print("Generating self-signed certificate for localhost...")
    print("This may take a moment...")
    
    # Generate private key
    subprocess.run([
        "openssl", "genrsa",
        "-out", str(key_file),
        "2048"
    ], check=True)
    
    # Generate self-signed certificate (valid for 365 days)
    subprocess.run([
        "openssl", "req", "-new", "-x509",
        "-key", str(key_file),
        "-out", str(cert_file),
        "-days", "365",
        "-subj", "/C=US/ST=Local/L=Local/O=Aperture MCP/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"
    ], check=True)
    
    print()
    print("✓ Certificate generated successfully!")
    print(f"  Key:  {key_file}")
    print(f"  Cert: {cert_file}")
    print()
    print("⚠️  IMPORTANT: Browser Security Warning")
    print("When you first connect, your browser will warn about the self-signed certificate.")
    print("This is expected. You need to:")
    print("  1. Click 'Advanced' or 'Show Details'")
    print("  2. Click 'Proceed to localhost (unsafe)' or 'Accept Risk'")
    print("  3. The connection will then be encrypted (even though self-signed)")
    print()
    print("For claude.ai connector:")
    print("  - Enter URL: https://127.0.0.1:8765/aperture-mcp-server.py")
    print("  - You may need to visit https://127.0.0.1:8765 in browser first to accept cert")
    
    return key_file, cert_file


class HTTPSApertureBridge(MCPFilesystemBridge):
    """Aperture bridge with HTTPS support."""
    
    def run_https(self, cert_file: Path, key_file: Path):
        """Start the MCP bridge server with HTTPS."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Starting MCP Bridge on https://localhost:{self.port}")
        logger.info(f"Using certificate: {cert_file}")
        logger.info(f"Session token: {self.session_token}")
        logger.info("")
        logger.info("⚠️  Browser will show security warning for self-signed cert")
        logger.info("   Click 'Advanced' → 'Proceed to localhost'")
        logger.info("")
        logger.info("For claude.ai Custom Connector:")
        logger.info(f"   URL: https://127.0.0.1:{self.port}/aperture-mcp-server.py")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        
        self.app.run(
            host='127.0.0.1',
            port=self.port,
            ssl_context=(str(cert_file), str(key_file)),
            debug=False
        )


def main():
    parser = argparse.ArgumentParser(
        description="Aperture Bridge - HTTPS-enabled MCP Filesystem for Web Claude"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Generate cert command
    cert_parser = subparsers.add_parser('generate-cert', help='Generate self-signed SSL certificate')
    cert_parser.add_argument(
        '--cert-dir',
        default=str(Path.home() / '.claude' / 'certs'),
        help='Directory for certificates (default: ~/.claude/certs)'
    )
    
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
    start_parser.add_argument(
        '--https',
        action='store_true',
        help='Enable HTTPS (required for web claude.ai)'
    )
    start_parser.add_argument(
        '--cert-dir',
        default=str(Path.home() / '.claude' / 'certs'),
        help='Directory for certificates (default: ~/.claude/certs)'
    )
    
    # Stop command (same as before)
    subparsers.add_parser('stop', help='Stop the bridge')
    
    # Status command (same as before)
    subparsers.add_parser('status', help='Check bridge status')
    
    args = parser.parse_args()
    
    if args.command == 'generate-cert':
        cert_dir = Path(args.cert_dir)
        generate_self_signed_cert(cert_dir)
    
    elif args.command == 'start':
        # Check if already running
        pid = load_pid()
        if pid and is_running(pid):
            print(f"Bridge already running (PID {pid})")
            sys.exit(1)
        
        # Start bridge
        if args.https:
            # Generate cert if needed
            cert_dir = Path(args.cert_dir)
            key_file, cert_file = generate_self_signed_cert(cert_dir)
            
            # Start HTTPS server
            bridge = HTTPSApertureBridge(
                allowed_dirs=args.allow,
                port=args.port
            )
            
            save_pid(os.getpid())
            
            try:
                bridge.run_https(cert_file, key_file)
            except KeyboardInterrupt:
                import logging
                logging.getLogger(__name__).info("\nShutting down...")
                pid_file = Path.home() / '.tam-bridge.pid'
                if pid_file.exists():
                    pid_file.unlink()
        else:
            # Start HTTP server (original aperture.py behavior)
            bridge = MCPFilesystemBridge(
                allowed_dirs=args.allow,
                port=args.port
            )
            
            save_pid(os.getpid())
            
            try:
                bridge.run()
            except KeyboardInterrupt:
                import logging
                logging.getLogger(__name__).info("\nShutting down...")
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
            
            pid_file = Path.home() / '.tam-bridge.pid'
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
            print("Connect browser to: http://localhost:8765 (HTTP)")
            print("              or to: https://localhost:8765 (HTTPS)")
        else:
            print(f"Bridge not running (stale PID {pid})")
            pid_file = Path.home() / '.tam-bridge.pid'
            if pid_file.exists():
                pid_file.unlink()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
    
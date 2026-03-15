/**
 * MCP Bridge Client - Browser Injection Script
 * 
 * Injects local filesystem MCP capabilities into claude.ai browser tab.
 * 
 * Usage:
 *   1. Start tam-bridge.py on localhost:8765
 *   2. Open claude.ai in browser
 *   3. Open browser console (F12)
 *   4. Paste and run this script
 *   5. Claude now has access to your local filesystem!
 * 
 * Security: Only connects to localhost. Session token required.
 */

(function() {
    'use strict';
    
    const BRIDGE_URL = 'http://localhost:8765';
    let sessionToken = null;
    let bridgeConnected = false;
    
    console.log('[MCP Bridge] Initializing...');
    
    /**
     * Authenticate with local bridge and get session token.
     */
    async function authenticate() {
        try {
            const res = await fetch(`${BRIDGE_URL}/auth`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });
            
            if (!res.ok) {
                throw new Error(`Auth failed: ${res.status}`);
            }
            
            const data = await res.json();
            sessionToken = data.token;
            
            console.log('[MCP Bridge] Authenticated ✓');
            console.log(`[MCP Bridge] Allowed directories:`, data.allowed_dirs);
            console.log(`[MCP Bridge] Token expires:`, data.expires);
            
            return true;
        } catch (err) {
            console.error('[MCP Bridge] Auth failed:', err.message);
            console.error('[MCP Bridge] Make sure tam-bridge.py is running on localhost:8765');
            return false;
        }
    }
    
    /**
     * Call MCP tool on local bridge.
     */
    async function callMCPTool(tool, params) {
        if (!sessionToken) {
            throw new Error('Not authenticated. Call authenticate() first.');
        }
        
        try {
            const res = await fetch(`${BRIDGE_URL}/mcp/${tool}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-MCP-Token': sessionToken
                },
                body: JSON.stringify(params)
            });
            
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${await res.text()}`);
            }
            
            const data = await res.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }
            
            return data;
        } catch (err) {
            console.error(`[MCP Bridge] ${tool} failed:`, err.message);
            throw err;
        }
    }
    
    /**
     * Create global MCP bridge object.
     */
    window.MCPBridge = {
        // Connection status
        get connected() { return bridgeConnected; },
        
        // Authenticate
        async connect() {
            bridgeConnected = await authenticate();
            return bridgeConnected;
        },
        
        // MCP Tool wrappers
        async readFile(path) {
            const result = await callMCPTool('read_file', {path});
            return result.content;
        },
        
        async writeFile(path, content) {
            const result = await callMCPTool('write_file', {path, content});
            return result.bytes_written;
        },
        
        async listDirectory(path) {
            const result = await callMCPTool('list_directory', {path});
            return result.entries;
        },
        
        async createDirectory(path) {
            const result = await callMCPTool('create_directory', {path});
            return result.path;
        },
        
        async moveFile(source, destination) {
            const result = await callMCPTool('move_file', {source, destination});
            return result;
        },
        
        async getFileInfo(path) {
            const result = await callMCPTool('get_file_info', {path});
            return result;
        },
        
        async listAllowedDirectories() {
            const result = await callMCPTool('list_allowed_directories', {});
            return result.allowed_directories;
        },
        
        // Helper: Read and parse JSON file
        async readJSON(path) {
            const content = await this.readFile(path);
            return JSON.parse(content);
        },
        
        // Helper: Write JSON file
        async writeJSON(path, obj) {
            const content = JSON.stringify(obj, null, 2);
            return await this.writeFile(path, content);
        }
    };
    
    // Auto-connect on injection
    window.MCPBridge.connect().then(connected => {
        if (connected) {
            console.log('[MCP Bridge] 🟢 Connected to local filesystem');
            console.log('[MCP Bridge] Available commands:');
            console.log('  MCPBridge.readFile(path)');
            console.log('  MCPBridge.writeFile(path, content)');
            console.log('  MCPBridge.listDirectory(path)');
            console.log('  MCPBridge.createDirectory(path)');
            console.log('  MCPBridge.listAllowedDirectories()');
            console.log('');
            console.log('Example:');
            console.log('  const dirs = await MCPBridge.listAllowedDirectories();');
            console.log('  const files = await MCPBridge.listDirectory(dirs[0]);');
        } else {
            console.log('[MCP Bridge] 🔴 Failed to connect');
            console.log('[MCP Bridge] Start tam-bridge.py and try again');
        }
    });
    
})();

"""
GitHub MCP Server for Cloud Run - Full MCP Protocol with Error Handling
"""
import asyncio
import logging
import os
import base64
import json
from typing import Any, Dict
import httpx
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, JSONResponse
from starlette.requests import Request as StarletteRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GitHub API configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"

# Create MCP server
mcp_server = Server("github-mcp-server")

@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available GitHub tools."""
    return [
        types.Tool(
            name="list_repositories",
            description="List all public repositories for a GitHub user",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "GitHub username"
                    }
                },
                "required": ["username"]
            }
        ),
        types.Tool(
            name="get_file_contents",
            description="Get contents of a file from a GitHub repository. Can also list directory contents if path is a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner username"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "path": {"type": "string", "description": "File path in repository (use README.md for readme, / or empty for root listing)"}
                },
                "required": ["owner", "repo", "path"]
            }
        ),
        types.Tool(
            name="get_repository_info",
            description="Get detailed information about a GitHub repository including description, stars, topics, and language",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner username"},
                    "repo": {"type": "string", "description": "Repository name"}
                },
                "required": ["owner", "repo"]
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    
    if name == "list_repositories":
        username = arguments.get("username")
        logger.info(f"Listing repos for {username}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/users/{username}/repos",
                    headers=headers
                )
                
                if response.status_code != 200:
                    return [types.TextContent(
                        type="text",
                        text=f"Error: HTTP {response.status_code} - {response.text}"
                    )]
                
                return [types.TextContent(type="text", text=response.text)]
                
            except Exception as e:
                logger.error(f"Error listing repositories: {e}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    elif name == "get_file_contents":
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        path = arguments.get("path", "")
        
        # Handle empty path or root directory
        if not path or path == "/":
            path = ""
        
        logger.info(f"Getting {path or 'root'} from {owner}/{repo}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
                    headers=headers
                )
                
                # Handle 404 - file not found
                if response.status_code == 404:
                    return [types.TextContent(
                        type="text",
                        text=f"File not found: {path or 'root'} in {owner}/{repo}. The file may not exist or the repository may be private."
                    )]
                
                # Handle other errors
                if response.status_code != 200:
                    return [types.TextContent(
                        type="text",
                        text=f"Error accessing file: HTTP {response.status_code}. {response.text[:200]}"
                    )]
                
                # Try to parse JSON
                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    return [types.TextContent(
                        type="text",
                        text=f"Error: GitHub API returned invalid JSON. Response: {response.text[:500]}"
                    )]
                
                # Handle directory listing (array response)
                if isinstance(data, list):
                    file_list = "\n".join([
                        f"- {item['name']} ({item['type']})" 
                        for item in data
                    ])
                    return [types.TextContent(
                        type="text",
                        text=f"Directory contents of {path or 'root'}:\n{file_list}"
                    )]
                
                # Handle file with content
                if "content" in data:
                    # Check if file is empty
                    if data.get("size", 0) == 0:
                        return [types.TextContent(
                            type="text",
                            text=f"File exists but is empty: {path}"
                        )]
                    
                    # Decode base64 content
                    try:
                        content = base64.b64decode(data["content"]).decode("utf-8")
                        return [types.TextContent(type="text", text=content)]
                    except Exception as e:
                        return [types.TextContent(
                            type="text",
                            text=f"Error decoding file content: {str(e)}"
                        )]
                
                # Return metadata if no content
                return [types.TextContent(
                    type="text",
                    text=json.dumps(data, indent=2)
                )]
                
            except httpx.TimeoutException:
                return [types.TextContent(
                    type="text",
                    text=f"Timeout accessing GitHub API for {owner}/{repo}/{path}"
                )]
            except Exception as e:
                logger.error(f"Error getting file contents: {e}", exc_info=True)
                return [types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    elif name == "get_repository_info":
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        logger.info(f"Getting info for {owner}/{repo}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
                    headers=headers
                )
                
                if response.status_code != 200:
                    return [types.TextContent(
                        type="text",
                        text=f"Error: HTTP {response.status_code} - {response.text[:200]}"
                    )]
                
                return [types.TextContent(type="text", text=response.text)]
                
            except Exception as e:
                logger.error(f"Error getting repository info: {e}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# Full MCP Protocol Handler
async def handle_mcp_request(request: StarletteRequest):
    """Handle MCP JSON-RPC requests with full protocol support."""
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        params = body.get("params", {})
        
        logger.info(f"MCP Request: {method}")
        
        # Handle initialize method
        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "logging": {}
                    },
                    "serverInfo": {
                        "name": "github-mcp-server",
                        "version": "0.1.0"
                    }
                }
            })
        
        # Handle initialized notification
        elif method == "notifications/initialized":
            return JSONResponse({"jsonrpc": "2.0"})
        
        # Handle tools/list
        elif method == "tools/list":
            tools = await handle_list_tools()
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        }
                        for tool in tools
                    ]
                }
            })
        
        # Handle tools/call
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            result = await handle_call_tool(tool_name, arguments)
            
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": item.type, "text": item.text}
                        for item in result
                    ]
                }
            })
        
        # Handle ping
        elif method == "ping":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            })
        
        # Unknown method
        else:
            logger.warning(f"Unknown method: {method}")
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }, status_code=200)
        
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}", exc_info=True)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }, status_code=200)

# Health check
async def health_check(request):
    """Health check endpoint."""
    return Response("OK", status_code=200)

# Create Starlette app
app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_mcp_request, methods=["POST"]),
        Route("/health", endpoint=health_check, methods=["GET"])
    ]
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 GitHub MCP server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

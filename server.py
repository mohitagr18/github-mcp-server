"""
GitHub MCP Server for Cloud Run - ADK Compatible
"""
import asyncio
import logging
import os
import base64
import json
from typing import Any
import httpx
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, JSONResponse
from starlette.requests import Request as StarletteRequest
from mcp.server.sse import SseServerTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GitHub API configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"

# Create MCP server
server = Server("github-mcp-server")

@server.list_tools()
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
            description="Get contents of a file from a GitHub repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "path": {
                        "type": "string",
                        "description": "File path in repository"
                    }
                },
                "required": ["owner", "repo", "path"]
            }
        ),
        types.Tool(
            name="get_repository_info",
            description="Get detailed information about a GitHub repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    }
                },
                "required": ["owner", "repo"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    
    if name == "list_repositories":
        username = arguments.get("username")
        logger.info(f"Listing repos for {username}")
        
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            response = await client.get(
                f"{GITHUB_API_BASE}/users/{username}/repos",
                headers=headers
            )
            return [types.TextContent(type="text", text=response.text)]
    
    elif name == "get_file_contents":
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        path = arguments.get("path")
        logger.info(f"Getting {path} from {owner}/{repo}")
        
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
                headers=headers
            )
            data = response.json()
            
            if "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8")
                return [types.TextContent(type="text", text=content)]
            return [types.TextContent(type="text", text=str(data))]
    
    elif name == "get_repository_info":
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        logger.info(f"Getting info for {owner}/{repo}")
        
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
                headers=headers
            )
            return [types.TextContent(type="text", text=response.text)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# MCP Message handler for POST requests
async def handle_messages(request: StarletteRequest):
    """Handle MCP messages via POST."""
    try:
        body = await request.json()
        logger.info(f"Received MCP request: {body.get('method', 'unknown')}")
        
        # Process the request through MCP server
        # This is a simplified handler - you may need to implement full MCP protocol
        method = body.get("method")
        
        if method == "tools/list":
            tools = await handle_list_tools()
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id"),
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
        
        elif method == "tools/call":
            params = body.get("params", {})
            result = await handle_call_tool(
                params.get("name"),
                params.get("arguments")
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "content": [
                        {"type": item.type, "text": item.text}
                        for item in result
                    ]
                }
            })
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })
        
    except Exception as e:
        logger.error(f"Error handling request: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)}
        }, status_code=500)

# Health check
async def health_check(request):
    """Health check endpoint."""
    return Response("OK", status_code=200)

# Create Starlette app
app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_messages, methods=["POST"]),  # Accept POST for ADK
        Route("/health", endpoint=health_check, methods=["GET"])
    ]
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 GitHub MCP server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

"""
GitHub MCP Server for Cloud Run with streamable HTTP transport.
"""
import asyncio
import logging
import os
import base64
from typing import Any
import httpx
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response
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

# Create SSE transport handler
async def handle_sse(request):
    """Handle SSE connections for MCP."""
    async with SseServerTransport("/messages") as transport:
        await server.run(
            transport,
            InitializationOptions(
                server_name="github-mcp-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
    return Response()

# Create Starlette app
app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/health", endpoint=lambda request: Response("OK", status_code=200))
    ]
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 GitHub MCP server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

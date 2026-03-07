"""MCP Server 启动入口（解决路径问题）"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.mcp_server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")

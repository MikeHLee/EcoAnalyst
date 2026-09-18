"""Compatibility entry point for MCP client configs that run this file directly. Prefer the `ecoanalyst-mcp` command."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))
from ecoanalyst.mcp_server import main
main()

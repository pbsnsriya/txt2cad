"""Start the txt2cad MCP server from any folder:  python /path/to/backend/run_mcp.py

An MCP client (Claude Code, Cursor, ...) runs this with its own working directory, so the backend folder is put on the path here instead of relying on it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()

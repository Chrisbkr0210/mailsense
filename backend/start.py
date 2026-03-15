"""Railway startup script — handles PORT env var explicitly."""
import os
import sys

port = int(os.environ.get("PORT", 8000))

import uvicorn
uvicorn.run("main:app", host="0.0.0.0", port=port)

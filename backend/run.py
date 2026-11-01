import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path so app can be imported from root or backend/
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn
from app.config import settings

if __name__ == "__main__":
    # Render provides PORT for deployed web services.
    is_render = "PORT" in os.environ

    host = "0.0.0.0" if is_render else (
        "127.0.0.1" if settings.app_mode == "local" else "0.0.0.0"
    )

    port = int(os.environ.get("PORT", settings.port))
    reload = not is_render and settings.app_mode == "local"

    print(f"Starting SoilMate on {host}:{port}...")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload
    )

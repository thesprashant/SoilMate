
import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    is_local = settings.app_mode == "local"

    host = "127.0.0.1" if is_local else "0.0.0.0"
    port = int(os.environ.get("PORT", settings.port))

    print(f"Starting SoilMate Backend on {host}:{port}...")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=is_local
    )

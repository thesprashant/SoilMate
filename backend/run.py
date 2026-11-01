
import os
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

    print(f"Starting SoilMate Backend on {host}:{port}...")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload
    )

"""Start the one shared cloud API; never seed or replace existing records."""
import os
import sys
from backend.photos import cloud_enabled, cloud_options
from backend.security import secret
from scripts.init_db import initialize

if __name__ == '__main__':
    secret()
    if not cloud_enabled():
        raise RuntimeError('Render free deployment requires PHOTO_STORAGE=cloudinary')
    cloud_options()
    initialize(seed=False)
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', os.getenv('PORT', '10000'), '--workers', '1', '--proxy-headers'])

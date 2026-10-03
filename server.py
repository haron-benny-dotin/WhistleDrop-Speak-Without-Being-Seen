import logging
import os

import uvicorn

from whistledrop.main import create_app

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    # access log off, otherwise it logs client IPs
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                access_log=False)

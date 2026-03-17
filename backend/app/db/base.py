import os
from dotenv import load_dotenv

load_dotenv(override=True)

_env = os.environ.get("ENV", "production")
_raw_url = os.environ.get("DATABASE_URL")

if _raw_url:
    DATABASE_URL = _raw_url
elif _env != "production":
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pncp"
else:
    raise RuntimeError(
        "DATABASE_URL is required when ENV=production. "
        "Set it in your Render environment variables."
    )

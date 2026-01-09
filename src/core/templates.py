"""Template configuration for server-side rendering."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

# Base directory for templates
BASE_DIR = Path(__file__).resolve().parent.parent

# Jinja2 templates instance (shared across routes)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

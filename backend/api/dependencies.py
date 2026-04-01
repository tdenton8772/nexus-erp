"""FastAPI shared dependencies."""
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db

# Re-export for use in route modules
__all__ = ["get_db", "AsyncSession"]

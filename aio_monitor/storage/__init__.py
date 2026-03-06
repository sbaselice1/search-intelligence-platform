"""Storage backends for monitoring results."""

from aio_monitor.storage.base import StorageBackend
from aio_monitor.storage.sqlite_store import SQLiteStore

__all__ = ["StorageBackend", "SQLiteStore"]

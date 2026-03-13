import psycopg
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from typing import Generator
from psycopg.rows import dict_row
from .base import DATABASE_URL

# Global connection pools
_request_pool = None
_job_pool = None

def _init_pools():
    """Initialize connection pools lazily."""
    global _request_pool, _job_pool
    if _request_pool is None:
        _request_pool = ConnectionPool(
            conninfo=DATABASE_URL, 
            min_size=2, 
            max_size=15, 
            kwargs={"autocommit": False, "row_factory": dict_row} # Explicitness for transactional requests
        )
    if _job_pool is None:
        _job_pool = ConnectionPool(
            conninfo=DATABASE_URL, 
            min_size=1, 
            max_size=5,
            kwargs={"autocommit": False, "row_factory": dict_row}
        )

def get_db() -> Generator[psycopg.Connection, None, None]:
    """
    Dependency for FastAPI requests. 
    Yields a connection from the request pool.
    """
    _init_pools()
    with _request_pool.connection() as conn:
        yield conn

@contextmanager
def get_job_conn() -> Generator[psycopg.Connection, None, None]:
    """
    Context manager for background jobs and long-running routines.
    """
    _init_pools()
    with _job_pool.connection() as conn:
        yield conn

def get_db_connection() -> psycopg.Connection:
    """
    Legacy helper for scripts and jobs that manage their own connection manually.
    Returns a new standalone connection bypassing the pool.
    Caller MUST call .close() on it.
    """
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

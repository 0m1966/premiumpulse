"""Factory providing active database client with automatic failover.

Checks whether live Snowflake credentials are valid and reachable;
otherwise falls back smoothly to the bundled offline snapshot.
"""

from functools import lru_cache
from typing import Any
from premiumpulse.config.settings import get_settings
from premiumpulse.db.snapshot_client import SnapshotClient


@lru_cache(maxsize=1)
def get_db_client() -> Any:
    """Retrieve singleton database client (Snowflake if live, else SnapshotClient)."""
    settings = get_settings()

    if settings.PREMIUMPULSE_MODE == "LIVE" and settings.is_snowflake_configured:
        try:
            from premiumpulse.db.snowflake_client import SnowflakeClient

            client = SnowflakeClient(settings)
            # Test connectivity with lightweight probe
            client.execute_query("SELECT 1;")
            return client
        except Exception as exc:
            # Fall back to offline snapshot if live connection times out or fails
            print(f"[WARN] Snowflake connection failed ({exc}). Falling back to SnapshotClient.")

    return SnapshotClient()


def get_current_mode() -> str:
    """Return operational mode string: LIVE or SNAPSHOT."""
    client = get_db_client()
    return "LIVE" if type(client).__name__ == "SnowflakeClient" else "SNAPSHOT"

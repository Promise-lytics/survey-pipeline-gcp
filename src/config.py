import os
from dataclasses import dataclass


@dataclass
class DBConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str = "require"

    def to_dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} sslmode={self.sslmode}"
        )


def get_db_config() -> DBConfig:
    """
    On Cloud Run, DB_PASSWORD is injected from Secret Manager via the
    --set-secrets flag. Locally, load from .env before running.
    """
    return DBConfig(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "surveys_db"),
        user=os.environ.get("DB_USER", "etl_user"),
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
    )


# GCS source — pipeline reads the latest export dropped here by SurveyCTO
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "exports/")

UPSERT_BATCH_SIZE = int(os.environ.get("UPSERT_BATCH_SIZE", "500"))

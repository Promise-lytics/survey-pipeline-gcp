import logging
import time
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from config import DBConfig, UPSERT_BATCH_SIZE
from transform import CleanRecord

logger = logging.getLogger(__name__)

SCHEMA = "surveys"

UPSERT_SQL = """
INSERT INTO surveys.survey_responses (
    surveycto_submission_id,
    survey_date,
    submission_timestamp,
    form_version,
    beneficiary_code,
    age_group,
    parity,
    agent_id,
    lga_id,
    community_name,
    method_id,
    first_time_user,
    counselling_provided,
    referral_made,
    quality_flag,
    updated_at
)
VALUES %s
ON CONFLICT (surveycto_submission_id) DO UPDATE SET
    survey_date          = EXCLUDED.survey_date,
    submission_timestamp = EXCLUDED.submission_timestamp,
    form_version         = EXCLUDED.form_version,
    age_group            = EXCLUDED.age_group,
    parity               = EXCLUDED.parity,
    agent_id             = EXCLUDED.agent_id,
    lga_id               = EXCLUDED.lga_id,
    community_name       = EXCLUDED.community_name,
    method_id            = EXCLUDED.method_id,
    first_time_user      = EXCLUDED.first_time_user,
    counselling_provided = EXCLUDED.counselling_provided,
    referral_made        = EXCLUDED.referral_made,
    quality_flag         = EXCLUDED.quality_flag,
    updated_at           = NOW()
WHERE (
    surveys.survey_responses.method_id            IS DISTINCT FROM EXCLUDED.method_id OR
    surveys.survey_responses.counselling_provided IS DISTINCT FROM EXCLUDED.counselling_provided OR
    surveys.survey_responses.quality_flag         IS DISTINCT FROM EXCLUDED.quality_flag
)
"""


def get_connection(cfg: DBConfig):
    return psycopg2.connect(cfg.to_dsn())


def _load_agent_map(cur) -> dict[str, int]:
    cur.execute(f"SELECT sister_code, agent_id FROM {SCHEMA}.field_agents")
    return {r[0]: r[1] for r in cur.fetchall()}


def _load_lga_map(cur) -> dict[str, int]:
    cur.execute(f"SELECT lga_name, lga_id FROM {SCHEMA}.lgas")
    return {r[0]: r[1] for r in cur.fetchall()}


def _load_method_map(cur) -> dict[str, int]:
    cur.execute(f"SELECT method_code, method_id FROM {SCHEMA}.contraceptive_methods")
    return {r[0]: r[1] for r in cur.fetchall()}


def _build_tuple(r: CleanRecord, agent_map, lga_map, method_map) -> tuple:
    return (
        r.surveycto_submission_id,
        r.survey_date,
        r.submission_timestamp,
        r.form_version,
        r.beneficiary_code,
        r.age_group,
        r.parity,
        agent_map.get(r.sister_code),
        lga_map.get(r.lga_name),
        r.community_name,
        method_map.get(r.method_code),
        r.first_time_user,
        r.counselling_provided,
        r.referral_made,
        r.quality_flag,
        datetime.utcnow(),
    )


def upsert_records(
    conn,
    records: list[CleanRecord],
    source_file: str,
    skipped: int = 0,
    rejected: int = 0,
) -> dict:
    start = time.time()
    run_id: Optional[int] = None
    stats = dict(inserted=0, updated=0, skipped=skipped, rejected=rejected)

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO surveys.etl_run_log (source_file, records_extracted, status)
                VALUES (%s, %s, 'running') RETURNING run_id
                """,
                (source_file, len(records) + skipped + rejected),
            )
            run_id = cur.fetchone()[0]

            agent_map  = _load_agent_map(cur)
            lga_map    = _load_lga_map(cur)
            method_map = _load_method_map(cur)

            for i in range(0, len(records), UPSERT_BATCH_SIZE):
                batch = records[i: i + UPSERT_BATCH_SIZE]
                tuples = [_build_tuple(r, agent_map, lga_map, method_map) for r in batch]
                psycopg2.extras.execute_values(cur, UPSERT_SQL, tuples, page_size=UPSERT_BATCH_SIZE)
                logger.info("upserted batch %d-%d", i, i + len(batch))

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE xmax = 0)  AS inserted,
                    COUNT(*) FILTER (WHERE xmax != 0) AS updated
                FROM surveys.survey_responses
                WHERE loaded_at > NOW() - INTERVAL '5 minutes'
                """
            )
            row = cur.fetchone()
            if row:
                stats["inserted"] = row[0]
                stats["updated"]  = row[1]

            duration = round(time.time() - start, 2)
            cur.execute(
                """
                UPDATE surveys.etl_run_log SET
                    records_inserted = %s,
                    records_updated  = %s,
                    records_skipped  = %s,
                    records_rejected = %s,
                    status           = 'success',
                    duration_seconds = %s
                WHERE run_id = %s
                """,
                (stats["inserted"], stats["updated"], stats["skipped"],
                 stats["rejected"], duration, run_id),
            )

    logger.info("load done — %s", stats)
    return stats

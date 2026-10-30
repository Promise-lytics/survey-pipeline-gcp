import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

VALID_METHODS   = {"IMPL", "IUD", "INJ", "COC", "POP", "COND", "EC"}
VALID_AGE_GROUPS = {"15-17", "18-24", "25-34", "35-44", "45-49"}


@dataclass
class CleanRecord:
    surveycto_submission_id: str
    survey_date: date
    submission_timestamp: Optional[datetime]
    form_version: Optional[str]
    beneficiary_code: str
    age_group: Optional[str]
    parity: Optional[int]
    sister_code: str
    state_code: str
    lga_name: str
    community_name: Optional[str]
    method_code: str
    first_time_user: Optional[bool]
    counselling_provided: bool
    referral_made: bool
    quality_flag: str


@dataclass
class TransformResult:
    clean: list[CleanRecord] = field(default_factory=list)
    skipped_duplicates: int = 0
    rejected_invalid: int = 0
    quality_warnings: int = 0


def _parse_bool(val: str) -> Optional[bool]:
    if val.lower() in ("yes", "true", "1"):
        return True
    if val.lower() in ("no", "false", "0"):
        return False
    return None


def _parse_date(val: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val.split("T")[0], fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _parse_timestamp(val: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(val)
    except (ValueError, AttributeError):
        return None


def transform(raw_rows: list[dict]) -> TransformResult:
    result = TransformResult()
    seen_ids: set[str] = set()

    for row in raw_rows:
        submission_id = row.get("KEY", "").strip()

        if not submission_id:
            result.rejected_invalid += 1
            continue

        if submission_id in seen_ids:
            result.skipped_duplicates += 1
            continue
        seen_ids.add(submission_id)

        sister_code = row.get("sister_code", "").strip()
        state_code  = row.get("state_code", "").strip()
        method_code = row.get("method_code", "").strip()
        raw_date    = row.get("SubmissionDate", "").strip()
        beneficiary = row.get("beneficiary_code", "").strip()

        if not all([sister_code, state_code, method_code, raw_date, beneficiary]):
            logger.warning("rejecting %s — missing required field(s)", submission_id)
            result.rejected_invalid += 1
            continue

        survey_date = _parse_date(raw_date)
        if survey_date is None:
            logger.warning("rejecting %s — unparseable date: %s", submission_id, raw_date)
            result.rejected_invalid += 1
            continue

        quality_flag = "clean"

        if method_code not in VALID_METHODS:
            quality_flag = "out_of_range"
            result.quality_warnings += 1

        age_group = row.get("age_group", "").strip() or None
        if age_group and age_group not in VALID_AGE_GROUPS:
            age_group = None
            quality_flag = "missing_fields"
            result.quality_warnings += 1

        parity_raw = row.get("parity", "").strip()
        try:
            parity = int(parity_raw)
            if not (0 <= parity <= 20):
                parity = None
                quality_flag = "out_of_range"
                result.quality_warnings += 1
        except (ValueError, TypeError):
            parity = None

        result.clean.append(CleanRecord(
            surveycto_submission_id=submission_id,
            survey_date=survey_date,
            submission_timestamp=_parse_timestamp(row.get("starttime", "")),
            form_version=row.get("formdef_version") or None,
            beneficiary_code=beneficiary,
            age_group=age_group,
            parity=parity,
            sister_code=sister_code,
            state_code=state_code,
            lga_name=row.get("lga_name", "").strip(),
            community_name=row.get("community") or None,
            method_code=method_code,
            first_time_user=_parse_bool(row.get("first_time_user", "")),
            counselling_provided=bool(_parse_bool(row.get("counselling_provided", "no"))),
            referral_made=bool(_parse_bool(row.get("referral_made", "no"))),
            quality_flag=quality_flag,
        ))

    logger.info(
        "transform done — clean=%d dup=%d rejected=%d warnings=%d",
        len(result.clean), result.skipped_duplicates,
        result.rejected_invalid, result.quality_warnings,
    )
    return result

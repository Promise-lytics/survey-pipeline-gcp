import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from transform import transform, CleanRecord


def _base_row(**overrides):
    row = {
        "KEY": "uuid-001",
        "sister_code": "CHW-KN-001",
        "state_code": "KN",
        "lga_name": "Kano Municipal",
        "method_code": "IMPL",
        "SubmissionDate": "2024-03-15",
        "beneficiary_code": "BEN-0001",
        "age_group": "18-24",
        "parity": "2",
        "counselling_provided": "yes",
        "referral_made": "no",
        "first_time_user": "yes",
        "starttime": "2024-03-15T10:30:00",
        "formdef_version": "v2.1",
        "community": "Gwale",
    }
    row.update(overrides)
    return row


def test_happy_path():
    result = transform([_base_row()])
    assert len(result.clean) == 1
    r = result.clean[0]
    assert r.surveycto_submission_id == "uuid-001"
    assert r.quality_flag == "clean"
    assert r.counselling_provided is True
    assert r.referral_made is False


def test_deduplication():
    rows = [_base_row(), _base_row()]
    result = transform(rows)
    assert len(result.clean) == 1
    assert result.skipped_duplicates == 1


def test_missing_key_rejected():
    result = transform([_base_row(KEY="")])
    assert result.rejected_invalid == 1
    assert len(result.clean) == 0


def test_missing_required_field_rejected():
    result = transform([_base_row(sister_code="")])
    assert result.rejected_invalid == 1


def test_bad_date_rejected():
    result = transform([_base_row(SubmissionDate="not-a-date")])
    assert result.rejected_invalid == 1


def test_unknown_method_flagged():
    result = transform([_base_row(method_code="UNKNOWN")])
    assert result.clean[0].quality_flag == "out_of_range"
    assert result.quality_warnings == 1


def test_unknown_age_group_nulled():
    result = transform([_base_row(age_group="10-14")])
    assert result.clean[0].age_group is None
    assert result.clean[0].quality_flag == "missing_fields"


def test_parity_out_of_range_nulled():
    result = transform([_base_row(parity="99")])
    assert result.clean[0].parity is None
    assert result.clean[0].quality_flag == "out_of_range"


def test_parity_non_numeric():
    result = transform([_base_row(parity="many")])
    assert result.clean[0].parity is None


def test_date_slash_format():
    result = transform([_base_row(SubmissionDate="15/03/2024")])
    from datetime import date
    assert result.clean[0].survey_date == date(2024, 3, 15)


def test_boolean_variants():
    result = transform([_base_row(counselling_provided="1", referral_made="false")])
    assert result.clean[0].counselling_provided is True
    assert result.clean[0].referral_made is False


def test_empty_input():
    result = transform([])
    assert result.clean == []
    assert result.rejected_invalid == 0


def test_whitespace_stripped():
    result = transform([_base_row(KEY="  uuid-001  ", sister_code="  CHW-KN-001  ")])
    assert result.clean[0].surveycto_submission_id == "uuid-001"
    assert result.clean[0].sister_code == "CHW-KN-001"


def test_optional_community_none():
    result = transform([_base_row(community="")])
    assert result.clean[0].community_name is None


def test_multiple_valid_rows():
    rows = [_base_row(KEY=f"uuid-{i:03d}", beneficiary_code=f"BEN-{i:04d}") for i in range(10)]
    result = transform(rows)
    assert len(result.clean) == 10
    assert result.skipped_duplicates == 0

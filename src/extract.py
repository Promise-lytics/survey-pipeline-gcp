import csv
import io
import logging

logger = logging.getLogger(__name__)


def parse_csv_text(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = [
        {k.strip(): v.strip() for k, v in row.items()}
        for row in reader
    ]
    logger.info("parsed %d rows from CSV", len(rows))
    return rows

import csv
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_conference_city_in_order(env: Any, config: Dict[str, Any]):
    """Read specific CSV file and extract column."""

    # NOTE: exact port of OSWorld logic.
    # Assumes 'csv_path' is a local path (host side) or has been downloaded?
    # In OSWorld calc.py just opens it. We assume the task setup ensures this file logic.

    csv_path = config.get("csv_path")
    if not csv_path:
        logger.error("No csv_path provided")
        return []

    logger.info(f"Reading csv file from {csv_path}")
    try:
        with open(csv_path, "r") as f:
            reader = csv.reader(f)
            # skip the header row
            next(reader, None)
            # get the third column (index 2)
            conference_city_list = [row[2] for row in reader if len(row) > 2]
            return conference_city_list
    except Exception as e:
        logger.error(f"Failed to read CSV {csv_path}: {e}")
        return []

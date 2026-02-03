"""General metrics for evaluation.

Core OSWorld-compatible metrics for comparing results with expected values.
"""

from typing import Any, Dict, List

from rapidfuzz import fuzz


def exact_match(result: Any, expected: Any = None, **options) -> float:
    """Exact string/value match.

    Args:
        result: The actual result
        expected: The expected value (or from options["expected"])
        options: May contain "expected" if not passed directly

    Returns:
        1.0 if match, 0.0 otherwise
    """
    if expected is None:
        expected = options.get("expected")

    if result == expected:
        return 1.0

    # Try string comparison
    if str(result).strip() == str(expected).strip():
        return 1.0

    return 0.0


def match_in_list(result: Any, expected: List[Any] = None, **options) -> float:
    """Check if result is in expected list.

    Args:
        result: The actual result
        expected: List of acceptable values (or from options["expected"])
        options: May contain "expected" and "rules"

    Returns:
        1.0 if result is in expected list, 0.0 otherwise
    """
    if expected is None:
        expected = options.get("expected", [])

    # Handle rules dict format
    if isinstance(expected, dict) and "expected" in expected:
        expected = expected["expected"]

    if not isinstance(expected, list):
        expected = [expected]

    if result in expected:
        return 1.0

    # Try string comparison
    result_str = str(result).strip().lower()
    for exp in expected:
        if str(exp).strip().lower() == result_str:
            return 1.0

    return 0.0


def is_in_list(result: Any, expected: List[Any] = None, **options) -> float:
    """Check if expected is in result (inverse of match_in_list).

    Args:
        result: The actual result (should be a list or string)
        expected: Value to find in result

    Returns:
        1.0 if expected is in result, 0.0 otherwise
    """
    if expected is None:
        expected = options.get("expected")

    if isinstance(result, (list, tuple)):
        return 1.0 if expected in result else 0.0

    if isinstance(result, str) and isinstance(expected, str):
        return 1.0 if expected in result else 0.0

    return 0.0


def fuzzy_match(result: Any, expected: Any = None, **options) -> float:
    """Fuzzy string matching using rapidfuzz.

    Args:
        result: The actual result
        expected: The expected value
        options: May contain "threshold" (default 85)

    Returns:
        1.0 if similarity >= threshold, 0.0 otherwise
    """
    if expected is None:
        expected = options.get("expected", "")

    threshold = options.get("threshold", 85)

    result_str = str(result).strip()
    expected_str = str(expected).strip()

    similarity = fuzz.ratio(result_str, expected_str)
    return 1.0 if similarity >= threshold else 0.0


def literal_match(result: Any, expected: Any = None, **options) -> float:
    """Literal match - alias for exact_match."""
    return exact_match(result, expected, **options)


def check_include_exclude(result: str, expected: Dict = None, **options) -> float:
    """Check if result includes required strings and excludes forbidden ones.

    Args:
        result: The string to check
        expected: Dict with "include" and/or "exclude" lists
        options: May contain "include" and "exclude"

    Returns:
        1.0 if all conditions met, 0.0 otherwise
    """
    include_list = options.get("include", [])
    exclude_list = options.get("exclude", [])

    if isinstance(expected, dict):
        include_list = expected.get("include", include_list)
        exclude_list = expected.get("exclude", exclude_list)

    result_str = str(result)

    # Check includes
    for item in include_list:
        if item not in result_str:
            return 0.0

    # Check excludes
    for item in exclude_list:
        if item in result_str:
            return 0.0

    return 1.0


def file_contains(result: str, expected: str = None, **options) -> float:
    """Check if file contains expected text.

    Args:
        result: Path to file or file content
        expected: Text to find

    Returns:
        1.0 if text found, 0.0 otherwise
    """
    import os

    if expected is None:
        expected = options.get("expected", "")

    content = result
    if os.path.isfile(result):
        try:
            with open(result, "r") as f:
                content = f.read()
        except Exception:
            return 0.0

    return 1.0 if expected in content else 0.0

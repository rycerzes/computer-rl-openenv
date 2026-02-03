"""OSWorld-compatible metrics registry.

Metrics compare results with expected values and return a score (0.0 to 1.0).
"""

from typing import Any, Callable

from .app_launched import evaluate_app_launched
from .file_exists import evaluate_file_exists
from .general import (
    check_include_exclude,
    exact_match,
    file_contains,
    fuzzy_match,
    is_in_list,
    literal_match,
    match_in_list,
)
from .process_running import evaluate_process_running
from .text_present import evaluate_text_present
from .url_match import evaluate_url_match

# Type alias for metric functions
Metric = Callable[..., float]

METRIC_REGISTRY: dict[str, Metric] = {
    # Legacy metrics (simple evaluators)
    "url_match": evaluate_url_match,
    "file_exists": evaluate_file_exists,
    "app_launched": evaluate_app_launched,
    "text_present": evaluate_text_present,
    "process_running": evaluate_process_running,
    # OSWorld-compatible metrics
    "exact_match": exact_match,
    "match_in_list": match_in_list,
    "is_in_list": is_in_list,
    "fuzzy_match": fuzzy_match,
    "literal_match": literal_match,
    "check_include_exclude": check_include_exclude,
    "file_contains": file_contains,
}


def evaluate_metric(metric_type: str, **kwargs: Any) -> float:
    """Evaluate using the specified metric.

    Args:
        metric_type: Name of the metric function
        **kwargs: Arguments passed to the metric

    Returns:
        Score from 0.0 to 1.0
    """
    metric_func = METRIC_REGISTRY.get(metric_type)
    if metric_func is None:
        raise ValueError(f"Unknown metric type: {metric_type}")
    result = metric_func(**kwargs)
    # Normalize to float
    if isinstance(result, bool):
        return 1.0 if result else 0.0
    return float(result)


def register_metric(name: str, metric_func: Metric) -> None:
    """Register a new metric function."""
    METRIC_REGISTRY[name] = metric_func


def list_metrics() -> list[str]:
    """List all registered metric names."""
    return list(METRIC_REGISTRY.keys())

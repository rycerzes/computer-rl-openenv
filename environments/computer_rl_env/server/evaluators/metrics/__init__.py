from typing import Any

from .app_launched import evaluate_app_launched
from .file_exists import evaluate_file_exists
from .process_running import evaluate_process_running
from .text_present import evaluate_text_present
from .url_match import evaluate_url_match

METRIC_REGISTRY = {
    "url_match": evaluate_url_match,
    "file_exists": evaluate_file_exists,
    "app_launched": evaluate_app_launched,
    "text_present": evaluate_text_present,
    "process_running": evaluate_process_running,
}


def evaluate_metric(metric_type: str, **kwargs: Any) -> bool:
    metric_func = METRIC_REGISTRY.get(metric_type)
    if metric_func is None:
        raise ValueError(f"Unknown metric type: {metric_type}")
    return metric_func(**kwargs)


def register_metric(name: str, metric_func: Any) -> None:
    METRIC_REGISTRY[name] = metric_func


def list_metrics() -> list[str]:
    return list(METRIC_REGISTRY.keys())

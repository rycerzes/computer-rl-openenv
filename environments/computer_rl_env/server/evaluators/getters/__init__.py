"""OSWorld-compatible getters for evaluation.

Getters fetch results from the environment for evaluation.
Each getter takes (env, config) and returns the result.
"""

from typing import Any, Callable, Dict

from .file import get_cache_file, get_vm_file
from .general import get_rule, get_vm_command_line

# Getter function type
Getter = Callable[[Any, Dict[str, Any]], Any]

# Registry of getters
GETTER_REGISTRY: Dict[str, Getter] = {
    "rule": get_rule,
    "vm_command_line": get_vm_command_line,
    "vm_file": get_vm_file,
    "cache_file": get_cache_file,
}


def register_getter(name: str, func: Getter) -> None:
    """Register a getter function."""
    GETTER_REGISTRY[name] = func


def get_result(getter_type: str, env: Any, config: Dict[str, Any]) -> Any:
    """Fetch result using the specified getter.

    Args:
        getter_type: Name of the getter (e.g., "vm_file", "default_search_engine")
        env: Environment instance with docker_provider
        config: Getter configuration from task evaluator

    Returns:
        The fetched result
    """
    getter_func = GETTER_REGISTRY.get(getter_type)
    if getter_func is None:
        raise ValueError(f"Unknown getter type: {getter_type}")
    return getter_func(env, config)


__all__ = [
    "GETTER_REGISTRY",
    "register_getter",
    "get_result",
    "get_rule",
    "get_vm_command_line",
    "get_vm_file",
    "get_cache_file",
]

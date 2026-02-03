"""General getters for evaluation."""

from typing import Any, Dict


def get_rule(env: Any, config: Dict[str, Any]) -> Any:
    """Get expected value from rules/config.

    This getter simply extracts a value from the config dict,
    used when the expected value is already known.

    Args:
        env: Environment instance (unused for this getter)
        config: Should contain the expected value directly

    Returns:
        The expected value from config
    """
    # For "rule" type, the config IS the expected value
    if "expected" in config:
        return config["expected"]
    return config


def get_vm_command_line(env: Any, config: Dict[str, Any]) -> str:
    """Execute a command in the VM and return output.

    Args:
        env: Environment instance with docker_provider
        config: Contains "command" - command to execute

    Returns:
        Command output as string
    """
    command = config.get("command", "")
    if isinstance(command, list):
        command = " ".join(command)

    # Execute via docker provider
    if hasattr(env, "docker_provider") and env.docker_provider:
        return env.docker_provider.execute(command)

    # Fallback: try subprocess if running locally
    import subprocess

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        return f"Error: {e}"


def get_vm_terminal_output(env: Any, config: Dict[str, Any]) -> str:
    """Get terminal output from VM.

    Similar to get_vm_command_line but may access stored terminal history.
    """
    return get_vm_command_line(env, config)

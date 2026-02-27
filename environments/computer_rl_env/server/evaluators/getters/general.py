"""General getters for evaluation."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


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


def get_vm_command_error(env: Any, config: Dict[str, Any]) -> str:
    """Execute a command in the VM and return stderr output.

    Like get_vm_command_line but captures stderr instead of stdout.

    Args:
        env: Environment instance with docker_provider
        config: Contains:
            - command: command string or list to execute
            - shell (bool): optional, whether to use shell (default False)

    Returns:
        stderr output as string, or None on failure
    """
    command = config.get("command", "")
    if isinstance(command, list):
        command = " ".join(command)

    # Execute via docker provider — use shell redirection to isolate stderr
    if hasattr(env, "docker_provider") and env.docker_provider:
        container = getattr(env.docker_provider, "container", None)
        if container:
            try:
                result = container.exec_run(["sh", "-c", f"{command} 2>&1 1>/dev/null"])
                return result.output.decode("utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Error executing command for stderr: {e}")
                return None
        # Fallback to execute() — but this only gives stdout
        return env.docker_provider.execute(command)

    # Fallback: try subprocess if running locally
    import subprocess

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stderr
    except Exception as e:
        return f"Error: {e}"


def get_vm_terminal_output(env: Any, config: Dict[str, Any]) -> str:
    """Get terminal output from VM.

    Prefer live terminal text extracted from accessibility tree.
    Falls back to latest observation and finally command output for compatibility.
    """
    try:
        parser = getattr(env, "accessibility_parser", None)
        if parser and hasattr(parser, "get_terminal_output"):
            output = parser.get_terminal_output()
            if output is not None:
                return output
    except Exception:
        pass

    try:
        prev_obs = getattr(env, "prev_observation", None)
        if prev_obs is not None:
            output = getattr(prev_obs, "terminal_output", None)
            if output is not None:
                return output
    except Exception:
        pass

    return get_vm_command_line(env, config)

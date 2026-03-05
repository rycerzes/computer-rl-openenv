import ast
import logging

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.basic_os")


def check_favorite_app(actual_favorites, rule):
    expected_apps = rule["expected"]
    # Removing 'org.gnome.' prefix if present for checking
    actual_apps_clean = [
        app.replace("org.gnome.", "").replace(".desktop", "") for app in actual_favorites
    ]

    for app in expected_apps:
        if app not in actual_apps_clean:
            return 0.0
    return 1.0


def check_gnome_favorite_apps(result, expected):
    expected_apps = expected.get("expected", expected) if isinstance(expected, dict) else expected
    if not isinstance(expected_apps, list):
        return 0.0

    apps = result
    if isinstance(result, str):
        try:
            apps = ast.literal_eval(result)
        except (ValueError, SyntaxError):
            return 0.0

    if not isinstance(apps, list):
        return 0.0

    if len(apps) != len(expected_apps):
        return 0.0
    return 1.0 if set(apps) == set(expected_apps) else 0.0


def check_utc_time(actual_time_output, rule):
    # Output from `timedatectl` expected
    if "Universal time" in actual_time_output:
        return 1.0
    return 0.0


def check_gnome_text_scaling_factor(actual_output, rule):
    expected_factor = float(rule["expected_factor"])
    try:
        # Expected output from gsettings get org.gnome.desktop.interface text-scaling-factor
        actual_factor = float(actual_output.strip().split()[-1])
        if abs(actual_factor - expected_factor) < 0.01:
            return 1.0
    except Exception as e:
        logger.error(f"Error checking gnome text scaling factor: {e}")
        pass
    return 0.0


def check_file_movement(file_list_output, rule):
    expected_file = rule["expected_file"]
    # file_list_output is expected to be a list of file paths or output of find command
    if expected_file in file_list_output:
        return 1.0
    return 0.0


def check_moved_jpgs(result, expected):
    expected_jpgs = expected.get("expected", expected) if isinstance(expected, dict) else expected
    if not isinstance(expected_jpgs, list):
        return 0.0

    if not isinstance(result, dict):
        return 0.0

    children = result.get("children", [])
    if not isinstance(children, list):
        return 0.0

    moved_jpgs = [
        node.get("name")
        for node in children
        if isinstance(node, dict) and node.get("type") == "file" and isinstance(node.get("name"), str)
    ]

    if len(moved_jpgs) != len(expected_jpgs):
        return 0.0
    return 1.0 if set(moved_jpgs) == set(expected_jpgs) else 0.0


def is_in_vm_clickboard(expected, result):
    """Check if expected content is present in the VM clipboard output.

    In OSWorld task JSONs:
    - 'expected' field -> getter that retrieves clipboard content (e.g. via xsel)
    - 'result' field -> rule dict containing {"rules": {"expected": "..."}}

    base.py resolves getters and calls: metric(result=<result_value>, expected=<expected_value>)
    So here: `expected` = clipboard output string, `result` = rule dict.
    """
    if result is None or expected is None:
        return 0.0

    # Extract the expected values from the rule config
    rules = result if not isinstance(result, dict) else result.get("rules", result)
    expected_results = rules.get("expected", rules) if isinstance(rules, dict) else rules

    # Check if clipboard output contains the expected content
    if not isinstance(expected_results, list):
        return 1.0 if str(expected_results) in str(expected) else 0.0
    else:
        return 1.0 if all(str(r) in str(expected) for r in expected_results) else 0.0

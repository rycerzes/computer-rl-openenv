import base64
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, TypeVar

import pytz
import requests

logger = logging.getLogger(__name__)

# Namespace maps from OSWorld
_accessibility_ns_map_ubuntu = {
    "st": "https://accessibility.ubuntu.example.org/ns/state",
    "attr": "https://accessibility.ubuntu.example.org/ns/attributes",
    "cp": "https://accessibility.ubuntu.example.org/ns/component",
    "doc": "https://accessibility.ubuntu.example.org/ns/document",
    "docattr": "https://accessibility.ubuntu.example.org/ns/document/attributes",
    "txt": "https://accessibility.ubuntu.example.org/ns/text",
    "val": "https://accessibility.ubuntu.example.org/ns/value",
    "act": "https://accessibility.ubuntu.example.org/ns/action",
}

# The accessibility extraction script to run inside the VM
# We assume python3-pyatspi and lxml are available.
# We inject /usr/lib/python3/dist-packages to path just in case for system packages.
ATSPI_SCRIPT = r"""
import sys
import site
# Ensure system packages like pyatspi are visible if we are in a venv
site.addsitedir("/usr/lib/python3/dist-packages")

import pyatspi
from pyatspi import StateType, STATE_SHOWING, Component, Text as ATText, Value as ATValue, Action as ATAction
import lxml.etree

# Constants
MAX_DEPTH = 50
MAX_WIDTH = 1024
ns_map = {
    "st": "https://accessibility.ubuntu.example.org/ns/state",
    "attr": "https://accessibility.ubuntu.example.org/ns/attributes",
    "cp": "https://accessibility.ubuntu.example.org/ns/component",
    "doc": "https://accessibility.ubuntu.example.org/ns/document",
    "docattr": "https://accessibility.ubuntu.example.org/ns/document/attributes",
    "txt": "https://accessibility.ubuntu.example.org/ns/text",
    "val": "https://accessibility.ubuntu.example.org/ns/value",
    "act": "https://accessibility.ubuntu.example.org/ns/action",
}

def _create_atspi_node(node, depth=0, flag=None):
    node_name = node.name
    attribute_dict = {"name": node_name}

    # States
    try:
        states = node.getState().get_states()
        for st in states:
            state_name = StateType._enum_lookup[st]
            state_name = state_name.split("_", maxsplit=1)[1].lower()
            if len(state_name) > 0:
                attribute_dict["{{{}}}{}".format(ns_map["st"], state_name)] = "true"
    except: pass

    # Attributes
    try:
        attributes = node.get_attributes()
        for k, v in attributes.items():
            if len(k) > 0:
                attribute_dict["{{{}}}{}".format(ns_map["attr"], k)] = v
    except: pass

    # Component
    try:
        if attribute_dict.get("{{{}}}visible".format(ns_map["st"]), "false") == "true" \
            and attribute_dict.get("{{{}}}showing".format(ns_map["st"]), "false") == "true":
            try:
                component = node.queryComponent()
                bbox = component.getExtents(pyatspi.XY_SCREEN)
                attribute_dict["{{{}}}screencoord".format(ns_map["cp"])] = str(tuple(bbox[0:2]))
                attribute_dict["{{{}}}size".format(ns_map["cp"])] = str(tuple(bbox[2:]))
            except NotImplementedError: pass
    except: pass

    text = ""
    # Text
    try:
        text_obj = node.queryText()
        text = text_obj.getText(0, text_obj.characterCount)
        text = text.replace("\ufffc", "").replace("\ufffd", "")
    except NotImplementedError: pass

    # Value
    try:
        value = node.queryValue()
        value_key = f"{{{ns_map['val']}}}"
        try: attribute_dict[f"{value_key}value"] = str(value.currentValue)
        except: pass
    except NotImplementedError: pass

    raw_role_name = node.getRoleName().strip()
    node_role_name = (raw_role_name or "unknown").replace(" ", "-")

    if not flag:
        if raw_role_name == "document spreadsheet": flag = "calc"
        if raw_role_name == "application" and node.name == "Thunderbird": flag = "thunderbird"

    xml_node = lxml.etree.Element(node_role_name, attrib=attribute_dict, nsmap=ns_map)
    if len(text) > 0:
        xml_node.text = text

    if depth == MAX_DEPTH: return xml_node

    try:
        for i, ch in enumerate(node):
            if i == MAX_WIDTH: break
            xml_node.append(_create_atspi_node(ch, depth + 1, flag))
    except: pass

    return xml_node

def main():
    try:
        # Retry logic for registry
        desktop = pyatspi.Registry.getDesktop(0)
        xml_root = _create_atspi_node(desktop)
        print(lxml.etree.tostring(xml_root, encoding="unicode"))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
"""


def get_accessibility_tree(env: Any, config: Dict[str, Any]) -> str:
    """Get accessibility tree as XML from the environment.

    Prefers the in-process ``AccessibilityParser.parse_xml()`` when available
    (running inside the container).  Falls back to docker-exec script injection
    for host-side evaluation.
    """
    # In-process path: use the parser directly (full parity, no HTTP overhead)
    if hasattr(env, "accessibility_parser"):
        try:
            xml_str = env.accessibility_parser.parse_xml()
            if xml_str:
                return xml_str
        except Exception as e:
            logger.warning("In-process accessibility tree failed, trying docker exec: %s", e)

    # Docker-exec fallback: inject ATSPI_SCRIPT into the container
    if hasattr(env, "docker_provider") and env.docker_provider:
        try:
            script_b64 = base64.b64encode(ATSPI_SCRIPT.encode()).decode()
            cmd = f"bash -c 'echo {script_b64} | base64 -d > /tmp/get_atspi.py && /usr/bin/python3 /tmp/get_atspi.py'"
            output = env.docker_provider.execute(cmd)

            if "ERROR:" in output and not output.strip().startswith("<"):
                logger.error(f"Accessibility script failed: {output}")
                return ""

            return output
        except Exception as e:
            logger.error(f"Failed to get accessibility tree: {e}")
            return ""

    return ""


# Time rule logic

R = TypeVar("Rule")

day_of_week_mapping = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

month_mapping = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

Month_Mapping_Full = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

month_mapping_full = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}

relative_time_to_int_day = {
    "tomorrow": 1,
    "5th next month": "special",
    "10th next month": "special",
    "11th next month": "special",
    "this month": "special",
    "this Saturday": "special",
    "this Sunday": "special",
    "next Monday": "special",
    "next Friday": "special",
    "next Saturday": "special",
    "next Sunday": "special",
    "next week Friday": "special",
    "next week Saturday": "special",
    "next week Sunday": "special",
    "first monday four months later": "special",
    "first monday eight months later": "special",
    "next Monday split": "special",
    "next Friday split": "special",
}


def get_rule(env, config: Dict[str, R]) -> R:
    """
    Returns the rule as-is.
    """
    return config["rules"]


def get_rule_relativetime(env, config: Dict[str, R]) -> R:
    """
    According to the rule definded in funciton "apply_rules_to_timeformat", convert the relative time to absolute time.
    config:
        'relativeTime': {
            "from": must exist; indicates the relativeTime.
            "to": optional; indicates the relativeTime.
        }
        If relativeTime only has key "from", then the key of time in "expected" dict must be "time".
        If relativeTime has key "to", then the key of time in "expected" dict must be "from" and "to".

        Optional 'timezone': timezone string like 'Europe/Zurich', 'America/New_York', etc.
        If not specified, will try to get timezone from IP geolocation.
    """
    logger.info(f"[DEBUG] get_rule_relativeTime called with config: {config}")

    relative_rules = config["rules"]
    relative_time = relative_rules["relativeTime"]  # int, "+" means future, "-" means past

    logger.info(f"[DEBUG] relativeTime: {relative_time}")

    # Get timezone configuration
    timezone_str = get_timezone_from_config(config)
    try:
        timezone = pytz.timezone(timezone_str)
        logger.info(f"Successfully loaded timezone: {timezone_str}")
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Unknown timezone: {timezone_str}, falling back to UTC")
        timezone = pytz.UTC

    # Get current time in the specified timezone
    now = datetime.now(timezone)
    logger.info(f"Current time in {timezone_str}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # calculate the relative time
    if "to" not in relative_time.keys():
        start_relative_time = relative_time["from"]
        logger.info(f"Processing single time: '{start_relative_time}'")

        if relative_time_to_int_day[start_relative_time] != "special":
            # relativeTime can be represented by actual int days
            start_relative_time_int_day = relative_time_to_int_day[start_relative_time]
            timediff = timedelta(days=start_relative_time_int_day)
            absolute_day = now + timediff
            logger.info(
                f"Simple calculation: {start_relative_time} = {start_relative_time_int_day} days -> {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
        else:
            # special case, you can add more special cases here
            if start_relative_time == "5th next month":
                next_year = now.year + 1 if now.month == 12 else now.year
                next_month = now.month + 1 if now.month < 12 else 1
                next_day = 5
                absolute_day = timezone.localize(datetime(next_year, next_month, next_day))
                logger.info(f"5th next month: {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            elif start_relative_time == "10th next month":
                next_year = now.year + 1 if now.month == 12 else now.year
                next_month = now.month + 1 if now.month < 12 else 1
                next_day = 10
                absolute_day = timezone.localize(datetime(next_year, next_month, next_day))
                logger.info(f"10th next month: {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            elif start_relative_time == "this month":
                absolute_day = now
                logger.info(f"This month: {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            elif start_relative_time == "next Monday":
                days_until_monday = (6 - now.weekday()) + 1
                absolute_day = now + timedelta(days=days_until_monday)
                logger.info(
                    f"Next Monday: current weekday={now.weekday()}, days to add={days_until_monday} -> {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif start_relative_time == "first monday four months later":
                next_year = now.year + 1 if now.month >= 9 else now.year
                next_month = (now.month + 4) % 12
                # get the first monday of the next_month
                temp_date = timezone.localize(datetime(next_year, next_month, 1))
                days_to_monday = ((6 - temp_date.weekday()) + 1) % 7
                absolute_day = temp_date + timedelta(days=days_to_monday)
                logger.info(
                    f"First Monday 4 months later: {next_year}-{next_month:02d} -> {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif start_relative_time == "first monday eight months later":
                next_year = now.year + 1 if now.month >= 5 else now.year
                next_month = (now.month + 8) % 12
                # get the first monday of the next_month
                temp_date = timezone.localize(datetime(next_year, next_month, 1))
                days_to_monday = ((6 - temp_date.weekday()) + 1) % 7
                absolute_day = temp_date + timedelta(days=days_to_monday)
                logger.info(
                    f"First Monday 8 months later: {next_year}-{next_month:02d} -> {absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            else:
                # Default fallback if special case matched but not implemented in this block (shouldn't happen with current dict)
                absolute_day = now

        regular_time = apply_rules_to_timeformat(relative_rules["expected"]["time"], absolute_day)
        logger.info(f"Final formatted time: {regular_time}")
        config["rules"]["expected"]["time"] = regular_time

    else:
        from_time = relative_time["from"]
        to_time = relative_time["to"]
        logger.info(f"Processing time range: from '{from_time}' to '{to_time}'")

        # deal with from_time first
        if relative_time_to_int_day[from_time] != "special":
            from_time_int_day = relative_time_to_int_day[from_time]
            from_timediff = timedelta(days=from_time_int_day)
            from_absolute_day = now + from_timediff
            logger.info(
                f"From time calculation: {from_time} = {from_time_int_day} days -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
        else:
            if from_time == "this Saturday":
                days_until_saturday = 5 - now.weekday()
                from_absolute_day = now + timedelta(days=days_until_saturday)
                logger.info(
                    f"This Saturday: current weekday={now.weekday()}, days to add={days_until_saturday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "10th next month":
                next_year = now.year + 1 if now.month == 12 else now.year
                next_month = now.month + 1 if now.month < 12 else 1
                next_day = 10
                from_absolute_day = timezone.localize(datetime(next_year, next_month, next_day))
                logger.info(
                    f"10th next month (from): {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next Monday" or from_time == "next Monday split":
                days_until_monday = (6 - now.weekday()) + 1
                from_absolute_day = now + timedelta(days=days_until_monday)
                logger.info(
                    f"Next Monday (from): current weekday={now.weekday()}, days to add={days_until_monday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next Friday":
                if now.weekday() < 4:  # Monday to Thursday
                    days_until_friday = 4 - now.weekday()
                elif now.weekday() == 4:  # Friday
                    days_until_friday = 7
                else:  # Saturday to Sunday
                    days_until_friday = (7 - now.weekday()) + 4
                from_absolute_day = now + timedelta(days=days_until_friday)
                logger.info(
                    f"Next Friday (from): current weekday={now.weekday()}, days to add={days_until_friday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next Saturday":
                if now.weekday() < 5:
                    days_until_saturday = 5 - now.weekday()
                elif now.weekday() == 5:
                    days_until_saturday = 7
                else:
                    days_until_saturday = 6
                from_absolute_day = now + timedelta(days=days_until_saturday)
                logger.info(
                    f"Next Saturday (from): current weekday={now.weekday()}, days to add={days_until_saturday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next week Friday":
                days_to_next_monday = 7 - now.weekday()
                days_until_friday = days_to_next_monday + 4
                from_absolute_day = now + timedelta(days=days_until_friday)
                logger.info(
                    f"Next week Friday (from): current weekday={now.weekday()}, days to add={days_until_friday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next week Saturday":
                days_to_next_monday = 7 - now.weekday()
                days_until_saturday = days_to_next_monday + 5
                from_absolute_day = now + timedelta(days=days_until_saturday)
                logger.info(
                    f"Next week Saturday (from): current weekday={now.weekday()}, days to add={days_until_saturday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif from_time == "next week Sunday":
                days_to_next_monday = 7 - now.weekday()
                days_until_sunday = days_to_next_monday + 6
                from_absolute_day = now + timedelta(days=days_until_sunday)
                logger.info(
                    f"Next week Sunday (from): current weekday={now.weekday()}, days to add={days_until_sunday} -> {from_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            else:
                from_absolute_day = now  # Fallback

        if from_time == "next Monday split":
            puday = apply_rules_to_timeformat(
                relative_rules["expected"]["puDay"], from_absolute_day
            )
            config["rules"]["expected"]["puDay"] = puday
            pumonth = apply_rules_to_timeformat(
                relative_rules["expected"]["puMonth"], from_absolute_day
            )
            config["rules"]["expected"]["puMonth"] = pumonth
            puyear = apply_rules_to_timeformat(
                relative_rules["expected"]["puYear"], from_absolute_day
            )
            config["rules"]["expected"]["puYear"] = puyear
            logger.info(
                f"Monday split formatting: puDay={puday}, puMonth={pumonth}, puYear={puyear}"
            )
        else:
            regular_from_time = apply_rules_to_timeformat(
                relative_rules["expected"]["from"], from_absolute_day
            )
            config["rules"]["expected"]["from"] = regular_from_time
            logger.info(f"From time formatted: {regular_from_time}")

        # deal with to_time
        if relative_time_to_int_day[to_time] != "special":
            to_time_int_date = relative_time_to_int_day[to_time]
            to_timediff = timedelta(days=to_time_int_date)
            to_absolute_day = now + to_timediff
            logger.info(
                f"To time calculation: {to_time} = {to_time_int_date} days -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
        else:
            if to_time == "this Sunday":
                days_until_sunday = 6 - now.weekday()
                to_absolute_day = now + timedelta(days=days_until_sunday)
                logger.info(
                    f"This Sunday: current weekday={now.weekday()}, days to add={days_until_sunday} -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif to_time == "11th next month":
                next_year = now.year + 1 if now.month == 12 else now.year
                next_month = now.month + 1 if now.month < 12 else 1
                next_day = 11
                to_absolute_day = timezone.localize(datetime(next_year, next_month, next_day))
                logger.info(
                    f"11th next month (to): {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            elif to_time == "next Friday" or to_time == "next Friday split":
                if from_time in ["next Monday", "next Monday split"]:
                    to_absolute_day = from_absolute_day + timedelta(days=4)
                    logger.info(
                        f"Next Friday (same week as Monday): from Monday {from_absolute_day.strftime('%Y-%m-%d')} + 4 days -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
                else:
                    if now.weekday() < 4:
                        days_to_friday = 4 - now.weekday()
                    else:
                        days_to_friday = (6 - now.weekday()) + 5
                    to_absolute_day = now + timedelta(days=days_to_friday)
                    logger.info(
                        f"Next Friday (standalone): current weekday={now.weekday()}, days to add={days_to_friday} -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
            elif to_time == "next Sunday":
                if from_time in ["next Friday", "next Saturday"]:
                    days_to_add_for_sunday = 6 - from_absolute_day.weekday()
                    to_absolute_day = from_absolute_day + timedelta(days=days_to_add_for_sunday)
                    logger.info(
                        f"Next Sunday (to, same weekend as {from_time}): from {from_absolute_day.strftime('%Y-%m-%d %A')} + {days_to_add_for_sunday} days -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
                else:
                    if now.weekday() < 6:
                        days_until_sunday = 6 - now.weekday()
                    else:
                        days_until_sunday = 7
                    to_absolute_day = now + timedelta(days=days_until_sunday)
                    logger.info(
                        f"Next Sunday (to, standalone): current weekday={now.weekday()}, days to add={days_until_sunday} -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
            elif to_time == "next week Sunday":
                if from_time in ["next week Friday", "next week Saturday"]:
                    days_to_add_for_sunday = 6 - from_absolute_day.weekday()
                    to_absolute_day = from_absolute_day + timedelta(days=days_to_add_for_sunday)
                    logger.info(
                        f"Next week Sunday (to, same week as {from_time}): from {from_absolute_day.strftime('%Y-%m-%d %A')} + {days_to_add_for_sunday} days -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
                else:
                    days_to_next_monday = 7 - now.weekday()
                    days_until_sunday = days_to_next_monday + 6
                    to_absolute_day = now + timedelta(days=days_until_sunday)
                    logger.info(
                        f"Next week Sunday (to, standalone): current weekday={now.weekday()}, days to add={days_until_sunday} -> {to_absolute_day.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
            else:
                to_absolute_day = now  # Fallback

        if to_time == "next Friday split":
            to_day = apply_rules_to_timeformat(relative_rules["expected"]["doDay"], to_absolute_day)
            config["rules"]["expected"]["doDay"] = to_day
            to_month = apply_rules_to_timeformat(
                relative_rules["expected"]["doMonth"], to_absolute_day
            )
            config["rules"]["expected"]["doMonth"] = to_month
            to_year = apply_rules_to_timeformat(
                relative_rules["expected"]["doYear"], to_absolute_day
            )
            config["rules"]["expected"]["doYear"] = to_year
            logger.info(
                f"Friday split formatting: doDay={to_day}, doMonth={to_month}, doYear={to_year}"
            )
        else:
            regular_to_time = apply_rules_to_timeformat(
                relative_rules["expected"]["to"], to_absolute_day
            )
            config["rules"]["expected"]["to"] = regular_to_time
            logger.info(f"To time formatted: {regular_to_time}")

    logger.info(f"[DEBUG] Final config rules: {config['rules']}")
    # print(config["rules"])
    return config["rules"]


def apply_rules_to_timeformat(time_format: str, absolute_day: datetime):
    time_format = time_format.replace("{DoW}", day_of_week_mapping[absolute_day.weekday()], 1)
    time_format = time_format.replace("{Month}", month_mapping[absolute_day.month], 1)
    time_format = time_format.replace("{DayD}", str(absolute_day.day), 1)
    time_format = time_format.replace("{Year}", str(absolute_day.year), 1)
    time_format = time_format.replace(
        "{Month0D}",
        "0" + str(absolute_day.month) if absolute_day.month < 10 else str(absolute_day.month),
        1,
    )
    time_format = time_format.replace("{month}", month_mapping_full[absolute_day.month], 1)
    time_format = time_format.replace("{MonthFull}", Month_Mapping_Full[absolute_day.month], 1)
    time_format = time_format.replace(
        "{Day0D}",
        "0" + str(absolute_day.day) if absolute_day.day < 10 else str(absolute_day.day),
        1,
    )
    time_format = time_format.replace("{MonthD}", str(absolute_day.month), 1)

    return time_format


def get_time_diff_range(env, config) -> str:
    try:
        return config["diff_range_in_minutes"]
    except Exception:
        logger.error("diff_range_in_minutes not found in config.")
        return None


def get_timezone_from_ip() -> str:
    """
    Get timezone from IP address using IP geolocation API
    Returns timezone string like 'Europe/Zurich' or 'UTC' as fallback
    """
    try:
        # Try ipapi.co first
        response = requests.get("https://ipapi.co/json/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            timezone = data.get("timezone")
            if timezone:
                logger.info(f"Timezone from IP: {timezone}")
                return timezone
    except Exception as e:
        logger.warning(f"Failed to get timezone from IP: {e}")

    # Fallback to UTC
    logger.info("Using UTC as fallback timezone")
    return "UTC"


def get_timezone_from_config(config: Dict, default_timezone: str = None) -> str:
    """
    Get timezone from config, with fallback options
    Priority: config timezone > default_timezone > IP-based timezone > UTC
    """
    # Check if timezone is specified in config
    if "timezone" in config.get("rules", {}):
        timezone = config["rules"]["timezone"]
        logger.info(f"Using timezone from config: {timezone}")
        return timezone

    # Use provided default
    if default_timezone:
        logger.info(f"Using provided default timezone: {default_timezone}")
        return default_timezone

    # Get from IP
    return get_timezone_from_ip()

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Match, Optional, Pattern, Union

from .utils import _match_record, _match_value_to_rule

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.thunderbird")

_pref_pattern: Pattern[str] = re.compile(r'^user_pref\("(?P<key>(?:[^"]|\\")+)", (?P<val>.+)\);$')


def check_thunderbird_prefs(
    result: Optional[str], rule: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> float:
    """
    Check Thunderbird preferences against expected rules.

    Args:
        result: path to result file
        rule: dict like
          {
            "expect": {
                str: {
                    "method": str
                    "ref": something
                }
            }
            "unexpect": {
                str: {
                    "method": str
                    "ref": something
                }
            }
          }

    Returns:
        float: 1.0 if all expectations are met, 0.0 otherwise
    """
    if result is None:
        return 0.0

    expect_rules = rule.get("expect", {})
    unexpect_rules = rule.get("unexpect", {})

    expect_metrics: Dict[str, bool] = {k: False for k in expect_rules}
    unexpect_metric = True
    with open(result) as f:
        for line in f:
            match_: Optional[Match[str]] = _pref_pattern.match(line.strip())
            if match_ is None:
                continue

            key: str = match_.group("key")
            value: Union[str, int, float, bool] = json.loads(match_.group("val"))
            if key in expect_rules:
                logger.debug("K: %s, V: %s", key, repr(value))
                expect_metrics[key] = _match_value_to_rule(value, dict(expect_rules[key]))  # type: ignore[arg-type]
            elif key in unexpect_rules:
                unexpect_metric = unexpect_metric and not _match_value_to_rule(
                    value,
                    dict(unexpect_rules[key]),  # type: ignore[arg-type]
                )

    return float(all(expect_metrics.values()) and unexpect_metric)


def _value_processor(val: str) -> str:
    """Process value by unescaping quotes and backslashes."""
    return val.replace('\\"', '"').replace("\\\\", "\\")


_condition_pattern: Pattern[str] = re.compile(
    r"\b(?:AND|OR) \((?:[\w ]+),(?:[\w " + "'" + r']+),(?:"(?:(?:[^"]|\")+)"|(?:[^)]+))\)|\bALL\b'
)


def check_thunderbird_filter(
    result: Optional[str], rules: Mapping[str, List[Mapping[str, Any]]]
) -> float:
    """
    Check Thunderbird filters against expected rules.

    Args:
        result: path to filter def file
        rules: dict like
          {
            "expect": [{key: value}]
            "unexpect": [{key: value}]
          }

    Returns:
        float: 1.0 if all expectations are met, 0.0 otherwise
    """
    if result is None:
        return 0.0

    # read filter def file
    # a filter:
    # {
    #   "name": "Name",
    #   "enabled": "yes" | "no",
    #   "type": "17",
    #   "action": "Move to folder" | ...,
    #   "actionValue": ...,
    #   "condition": [...]
    # }
    filters: List[Dict[str, Union[str, List[str]]]] = []
    filter_: Dict[str, Union[str, List[str]]] = {}
    with open(result) as f:
        for line in f:
            if line.startswith("name="):
                filter_ = {}
                filter_["name"] = _value_processor(line[6:-2])
            elif line.startswith("enabled="):
                filter_["enabled"] = _value_processor(line[9:-2])
            elif line.startswith("type="):
                filter_["type"] = _value_processor(line[6:-2])
            elif line.startswith("action="):
                filter_["action"] = _value_processor(line[8:-2])
            elif line.startswith("actionValue="):
                filter_["actionValue"] = _value_processor(line[13:-2])
            elif line.startswith("condition="):
                condition_str: str = _value_processor(line[11:-2])
                logger.debug("FILTER CONDITION: %s", condition_str)

                conditions: List[str] = _condition_pattern.findall(condition_str)
                logger.debug("FILTER CONDITIONS: %s", repr(conditions))

                filter_["condition"] = conditions
                logger.debug("FILTER %s", repr(filter_))
                filters.append(filter_)

    expect_metrics = [False] * len(rules.get("expect", []))
    unexpect_metric = True
    for flt in filters:
        for i, r in enumerate(rules.get("expect", [])):
            expect_metrics[i] = expect_metrics[i] or _match_record(dict(r), dict(flt))  # type: ignore[arg-type]
        unexpect_metric = unexpect_metric and not any(
            _match_record(dict(r), dict(flt))  # type: ignore[arg-type]
            for r in rules.get("unexpect", [])
        )
    return float(all(expect_metrics) and unexpect_metric)


def check_thunderbird_folder(
    result: Union[str, List[str]], reference: Union[str, List[str]], **kwargs: bool
) -> float:
    """
    Check the file or file_list that each text file contains all messages in a folder in Thunderbird.

    Each message is started with `FROM - `.

    Args:
        result: file path or list of file paths
        reference: file path or list of file paths
        **kwargs:
            ignore_status: for comparison, ignore the status (X-Mozilla-Status: 0000).
                          default: False
            ignore_keys: for comparison, ignore the keys (X-Mozilla-Keys: label).
                        default: False
            remove_deleted: ignore deleted messages which has status code 0008 or 0009.
                           default: True
            remove_duplicate: remove duplicate messages. default: True

    Returns:
        float: 1.0 if all messages match, 0.0 otherwise
    """

    def normalize_msg(msg: str, options: Dict[str, bool]) -> str:
        """Normalize a message for comparison."""
        ignore_status = options.get("ignore_status", False)
        ignore_keys = options.get("ignore_keys", False)
        if ignore_status:
            msg = re.sub(r"X-Mozilla-Status\d?:[\s\d]+", "", msg)
        if ignore_keys:
            msg = re.sub(r"(X-Mozilla-Keys:[^\n]*?)\n(MIME-Version)", r"\2", msg)
        return msg.strip()

    def read_thunderbird_folder_file(path: str) -> str:
        """Read and normalize Thunderbird folder file."""
        with open(path, "r") as inf:
            data = inf.read().strip()
            messages: List[str] = []
            for mail in data.split("FROM - "):
                if not mail.strip():
                    continue
                if kwargs.get("remove_deleted", True) and re.search(
                    r"X-Mozilla-Status: 000[89]", mail
                ):
                    continue
                messages.append("FROM - " + normalize_msg(mail, kwargs))

            if kwargs.get("remove_duplicate", True):
                messages_set = set(messages)
                return "\n".join(sorted(messages_set))
            return "\n".join(sorted(messages))

    result_list: List[str]
    reference_list: List[str]
    if not isinstance(reference, list):
        result_list, reference_list = [result], [reference]  # type: ignore[list-item]
    else:
        result_list = result if isinstance(result, list) else [result]
        reference_list = reference

    for pred, gold in zip(result_list, reference_list):
        if pred is None:
            return 0.0
        mail1 = read_thunderbird_folder_file(pred)
        mail2 = read_thunderbird_folder_file(gold)
        if mail1 != mail2:
            return 0.0
    return 1.0

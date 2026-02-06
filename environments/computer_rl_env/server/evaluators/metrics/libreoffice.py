import logging
import os
import xml.etree.ElementTree as ET

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.libreoffice")


def check_libre_locale(actual_config_path, rule):
    expected_locale = rule["expected_locale"]

    if not os.path.exists(actual_config_path):
        return 0.0

    try:
        tree = ET.parse(actual_config_path)
        root = tree.getroot()

        # This is strictly based on how it was in OSWorld, but simplified for brevity if needed
        # The original code parses registrymodifications.xcu
        # We'll assume the same structure for now
        namespaces = {
            "oor": "http://openoffice.org/2001/registry",
            "xs": "http://www.w3.org/2001/XMLSchema",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }

        for item in root.findall(".//item", namespaces):
            path = item.get("{http://openoffice.org/2001/registry}path")
            if path == "/org.openoffice.Setup/L10N":
                prop = item.find(".//prop[@oor:name='ooSetupSystemLocale']", namespaces)
                if prop is not None:
                    value = prop.find("value").text
                    if value == expected_locale:
                        return 1.0

        return 0.0
    except Exception as e:
        logger.error(f"Error checking locale: {e}")
        return 0.0

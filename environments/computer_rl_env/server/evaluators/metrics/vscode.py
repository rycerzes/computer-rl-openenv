import importlib.util
import json
import logging
import os
import re
import sys
import uuid
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.vscode")


def check_json_keybindings(actual: str, expected: Dict[str, Any], **options: Any) -> float:
    """
    Check if expected keybinding exists in the JSON keybindings file.

    Args:
        actual: path to result JSON keybindings file
        expected: dict containing "expected" key with the expected keybinding dict

    Return:
        1.0 if expected keybinding is found, 0.0 otherwise
    """
    if not actual:
        return 0.0

    def direct_load_json(fp: str) -> Optional[List[Dict[str, Any]]]:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
            return data
        except Exception:
            return None

    def skip_first_line_load_json(fp: str) -> Optional[List[Dict[str, Any]]]:
        try:
            with open(fp, "r") as f:
                f.readline()
                data = json.load(f)
            return data
        except Exception:
            return None

    for func in [direct_load_json, skip_first_line_load_json]:
        data = func(actual)
        if data is not None and isinstance(data, list):
            break
    else:
        return 0.0

    expected_binding = expected.get("expected")
    if expected_binding in data:
        return 1.0
    else:
        return 0.0


def check_json_settings(actual: str, expected: Dict[str, Any], **options: Any) -> float:
    """
    Check if expected settings exist in the JSON settings file.

    Args:
        actual: path to result JSON settings file
        expected: dict containing "expected" key with expected settings dict

    Return:
        1.0 if all expected settings match, 0.0 otherwise
    """
    if not actual:
        return 0.0

    try:
        with open(actual, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.debug(f"Failed to load JSON settings: {e}")
        return 0.0

    expect = expected.get("expected", {})

    # Check if all expected key-value pairs are in the actual data
    for key, value in expect.items():
        if key not in data or data[key] != value:
            return 0.0

    return 1.0


def compare_text_file(actual: str, expected: str, **options: Any) -> float:
    """
    Compare two text files with optional ignore_blanks and ignore_case options.

    Args:
        actual: path to result text file
        expected: path to gold text file

    Return:
        1.0 if files match, 0.0 otherwise
    """
    if not actual:
        return 0.0

    try:
        with open(actual) as f1:
            actual_text = f1.read()
        with open(expected) as f2:
            expected_text = f2.read()
    except Exception as e:
        logger.debug(f"Failed to read text files: {e}")
        return 0.0

    ignore_blanks = options.get("ignore_blanks", False)
    if ignore_blanks:
        actual_text = re.sub(r"[\t\n]", " ", actual_text).strip()
        actual_text = re.sub(r"\s+", " ", actual_text)
        expected_text = re.sub(r"[\t\n]", " ", expected_text).strip()
        expected_text = re.sub(r"\s+", " ", expected_text)

    ignore_case = options.get("ignore_case", False)
    if ignore_case:
        actual_text = actual_text.lower()
        expected_text = expected_text.lower()

    if actual_text == expected_text:
        return 1.0
    return 0.0


def compare_pdf_content(content1: bytes, content2: bytes, text_similarity_threshold: float) -> bool:
    """
    Compare PDF content by extracting text and computing similarity ratio.

    Args:
        content1: first PDF file content as bytes
        content2: second PDF file content as bytes
        text_similarity_threshold: minimum similarity ratio to consider PDFs equal

    Return:
        True if similarity ratio exceeds threshold, False otherwise
    """
    if PyPDF2 is None:
        logger.warning("PyPDF2 not installed, cannot compare PDF content")
        return False

    def extract_text_from_pdf(content: bytes) -> str:
        assert PyPDF2 is not None  # Type guard for Pylance
        with open("temp.pdf", "wb") as temp_pdf:
            temp_pdf.write(content)
        with open("temp.pdf", "rb") as temp_pdf:
            pdf_reader = PyPDF2.PdfReader(temp_pdf)
            text = ""
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text()
        return text

    text1 = extract_text_from_pdf(content1)
    text2 = extract_text_from_pdf(content2)

    similarity_ratio = SequenceMatcher(None, text1, text2).ratio()

    return similarity_ratio >= text_similarity_threshold


def compare_zip_files(actual: str, expected: str, **options: Any) -> float:
    """
    Compare two zip files by comparing file lists and content.

    Args:
        actual: path to result zip file
        expected: path to gold zip file

    Return:
        1.0 if zip files are identical, 0.0 otherwise
    """
    if not actual:
        return 0.0

    try:
        with zipfile.ZipFile(actual, "r") as zip_file1, zipfile.ZipFile(expected, "r") as zip_file2:
            file_list1 = set(zip_file1.namelist())
            file_list2 = set(zip_file2.namelist())

            if file_list1 != file_list2:
                return 0.0

            for file_name in file_list1:
                content1 = zip_file1.read(file_name)
                content2 = zip_file2.read(file_name)

                if file_name.lower().endswith(".pdf"):
                    if compare_pdf_content(content1, content2, 0.95):
                        continue
                    else:
                        return 0.0
                elif content1 != content2:
                    return 0.0
        return 1.0
    except Exception as e:
        logger.debug(f"Failed to compare zip files: {e}")
        return 0.0


def _is_subset(expected: Any, actual: Any) -> bool:
    """
    Check if expected is a subset of actual (recursive for dicts).

    Args:
        expected: expected value or structure
        actual: actual value or structure

    Return:
        True if expected is a subset of actual
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for k, v in expected.items():
            if k not in actual:
                return False
            if not _is_subset(v, actual[k]):
                return False
        return True

    if isinstance(expected, list):
        return expected == actual

    return expected == actual


def compare_config(actual: str, rules: Dict[str, Any], **options: Any) -> float:
    """
    Compare configuration file with expected content.

    Args:
        actual: path to result config file
        rules: dict containing "expected" key with expected config content

    Return:
        1.0 if config matches, 0.0 otherwise
    """
    if not actual:
        return 0.0

    expected_text = rules.get("expected")
    if not expected_text:
        return 0.0

    try:
        with open(actual, "r", encoding="utf-8") as f:
            actual_text = f.read()
    except Exception as e:
        logger.debug(f"Failed to read config file: {e}")
        return 0.0

    # Containment option (default True => loose/containment semantics)
    containment_ok = options.get("containment_ok", True)

    if containment_ok:
        # Prefer robust JSON subset check
        try:
            actual_json = json.loads(actual_text)
            expected_json = json.loads(expected_text)
            if _is_subset(expected_json, actual_json):
                return 1.0
        except Exception:
            # Fallback: substring containment
            if expected_text.strip() in actual_text:
                return 1.0
        return 0.0

    # Strict legacy behavior
    if actual_text == expected_text:
        return 1.0

    # Optional: JSON equality ignoring formatting (still strict on extra keys)
    try:
        if json.loads(actual_text) == json.loads(expected_text):
            return 1.0
    except Exception:
        pass

    return 0.0


def compare_answer(actual: str, rules: Dict[str, Any], **options: Any) -> float:
    """
    Compare actual string with expected answer.

    Args:
        actual: result string
        rules: dict containing "expected" key with expected answer

    Return:
        1.0 if answers match, 0.0 otherwise
    """
    if not actual:
        return 0.0

    if actual == rules.get("expected"):
        return 1.0

    # TODO: can use text embedding to get non-zero return
    return 0.0


def is_extension_installed(actual: str, rules: Dict[str, Any], **options: Any) -> float:
    """
    Check if an extension is installed or not installed based on type.

    Args:
        actual: string to search in (e.g., extension list)
        rules: dict with "type" ("contain" or "not_contain") and "expected" (string to search for)

    Return:
        1.0 if condition is met, 0.0 otherwise
    """
    rule_type = rules.get("type")
    expected_value = rules.get("expected")

    if not expected_value:
        return 0.0

    if rule_type == "contain":
        if expected_value in actual:
            return 1.0
        return 0.0
    elif rule_type == "not_contain":
        if expected_value not in actual:
            return 1.0
        return 0.0
    else:
        raise NotImplementedError(f"Unknown rule type: {rule_type}")


def check_python_file_by_test_suite(
    actual_files: Optional[str], test_file: str, **options: Any
) -> float:
    """
    Check the python file by running the test suite in the given test file.

    This function is robust and handles various error conditions:
    - File existence validation
    - Module loading errors
    - Function execution errors
    - Proper resource cleanup
    - Working directory management

    Args:
        actual_files: path to the actual Python file(s) (not used directly)
        test_file: path to the test file to run

    Return:
        1.0 if test passes, 0.0 otherwise
    """
    test_function_name = options.get("test_function_name", "test")

    # Validate inputs
    if not test_file:
        logger.error("test_file is None or empty")
        return 0.0

    # Convert to absolute path and check existence
    test_file_path = Path(test_file).resolve()
    if not test_file_path.exists():
        logger.error(f"Test file does not exist: {test_file_path}")
        return 0.0

    if not test_file_path.is_file():
        logger.error(f"Test file path is not a file: {test_file_path}")
        return 0.0

    # Create unique module name to avoid conflicts
    module_name = f"dynamic_test_module_{uuid.uuid4().hex[:8]}"

    # Store original working directory and sys.path
    original_cwd = os.getcwd()
    original_sys_path = sys.path.copy()

    try:
        # Change to the directory containing the test file
        test_dir = test_file_path.parent
        os.chdir(test_dir)
        logger.debug(f"Changed working directory to: {test_dir}")

        # Add test directory to Python path if not already present
        if str(test_dir) not in sys.path:
            sys.path.insert(0, str(test_dir))
            logger.debug(f"Added {test_dir} to sys.path")

        # Try to load the module
        try:
            spec = importlib.util.spec_from_file_location(module_name, test_file_path)
            if spec is None:
                logger.error(f"Could not create module spec for {test_file_path}")
                return 0.0

            if spec.loader is None:
                logger.error(f"Module spec has no loader for {test_file_path}")
                return 0.0

            module = importlib.util.module_from_spec(spec)
            if module is None:
                logger.error(f"Could not create module from spec for {test_file_path}")
                return 0.0

            # Add to sys.modules temporarily
            sys.modules[module_name] = module

            # Execute the module
            spec.loader.exec_module(module)
            logger.debug(f"Successfully loaded test module: {module_name}")

        except SyntaxError as e:
            logger.error(f"Syntax error in test file: {e}")
            return 0.0
        except ImportError as e:
            logger.error(f"Import error loading test file: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Error loading test module: {e}")
            return 0.0

        # Try to get the test function
        try:
            if not hasattr(module, test_function_name):
                logger.error(f"Test function '{test_function_name}' not found in {test_file_path}")
                return 0.0

            test_function = getattr(module, test_function_name)

            if not callable(test_function):
                logger.error(f"'{test_function_name}' is not callable in {test_file_path}")
                return 0.0

            logger.debug(f"Found test function: {test_function_name}")

        except Exception as e:
            logger.error(f"Error getting test function: {e}")
            return 0.0

        # Execute the test function
        try:
            result = test_function()
            logger.debug(f"Test function returned: {result} (type: {type(result)})")

            # Handle different return types
            if isinstance(result, bool):
                return 1.0 if result else 0.0
            elif isinstance(result, (int, float)):
                # Normalize to 0.0-1.0 range
                normalized = max(0.0, min(1.0, float(result)))
                if normalized != result:
                    logger.warning(f"Test result {result} normalized to {normalized}")
                return normalized
            else:
                # For any other type, treat as True if truthy
                bool_result = bool(result)
                logger.warning(
                    f"Test returned non-boolean/numeric value {result}, treating as {bool_result}"
                )
                return 1.0 if bool_result else 0.0

        except Exception as e:
            logger.error(f"Error executing test function: {e}")
            return 0.0

    except Exception as e:
        logger.error(f"Unexpected error in check_python_file_by_test_suite: {e}")
        return 0.0

    finally:
        # Cleanup: remove the module from sys.modules
        if module_name in sys.modules:
            del sys.modules[module_name]
            logger.debug(f"Cleaned up module: {module_name}")

        # Restore original working directory
        try:
            os.chdir(original_cwd)
            logger.debug(f"Restored working directory to: {original_cwd}")
        except Exception as e:
            logger.warning(f"Could not restore working directory: {e}")

        # Restore original sys.path
        sys.path[:] = original_sys_path
        logger.debug("Restored sys.path")


def check_python_file_by_gold_file(
    actual_files: Optional[str], gold_file: str, **options: Any
) -> float:
    """
    Check the python file against a gold file.

    Args:
        actual_files: path to the actual Python file(s)
        gold_file: path to the gold/reference file

    Return:
        Score between 0.0 and 1.0
    """
    # TODO: Implement comparison logic
    return 0.0


def check_html_background_image(src_path: str, rule: Optional[Dict[str, Any]] = None) -> float:
    """
    Check if the background image is correctly set in HTML.

    Args:
        src_path: path to HTML file
        rule: dict containing "value" key with expected background image URL

    Return:
        1.0 if background image is found, 0.0 otherwise
    """
    if not src_path or not rule:
        return 0.0

    if BeautifulSoup is None:
        logger.warning("BeautifulSoup not installed, cannot check HTML background image")
        return 0.0

    try:
        with open(src_path, "r") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")
        styles = soup.find_all("style")
        expected_value = rule.get("value", "")

        for style in styles:
            if f"background-image: url('{expected_value}')" in style.text:
                return 1.0
        return 0.0
    except Exception as e:
        logger.debug(f"Failed to check HTML background image: {e}")
        return 0.0


def compare_result_files(src_path: str, tgt_path: str) -> float:
    """
    Compare whether the content of two files are the same.

    Args:
        src_path: path to source file
        tgt_path: path to target file

    Return:
        1.0 if files match (or target is contained in source), 0.0 otherwise
    """
    if not src_path or not tgt_path:
        return 0.0

    try:
        with open(src_path, "r") as f:
            src_content = f.read().strip()
        with open(tgt_path, "r") as f:
            tgt_content = f.read().strip()
    except Exception as e:
        logger.debug(f"Failed to read result files: {e}")
        return 0.0

    try:
        # Compare the content as numbers
        tgt_content_num = float(tgt_content)
        if tgt_content in src_content:
            # If the content of tgt is in src, return 1.0 since output src might be
            # a superset (language description + number) of tgt
            return 1.0
        src_content_num = float(src_content)
        if abs(src_content_num - tgt_content_num) < 1e-4:
            return 1.0
        return 0.0
    except Exception:
        if src_content == tgt_content:
            return 1.0
    return 0.0

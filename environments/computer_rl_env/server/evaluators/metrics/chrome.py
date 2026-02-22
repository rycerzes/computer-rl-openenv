"""Chrome metrics for evaluation.

Adapted from OSWorld/ComputerRL Chrome metrics. These are mostly pure-logic functions
that compare getter results against expected values.
"""

import io
import logging
import os
import re
import shutil
from itertools import product
from typing import Any, Dict, List, Union

import fitz
import imagehash
import rapidfuzz.fuzz as fuzz
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .utils import are_lists_equal, compare_urls

logger = logging.getLogger(__name__)


def is_expected_active_tab(active_tab_info: Dict[str, str], rule: Dict[str, Any]) -> float:
    """Check if the expected active tab is open in Chrome."""
    if not active_tab_info:
        return 0.0

    match_type = rule["type"]
    if match_type == "url":
        expected_url = rule["url"]
        actual_url = (
            active_tab_info.get("url", None) if isinstance(active_tab_info, dict) else active_tab_info
        )
        logger.info("expected_url: %s", expected_url)
        logger.info("actual_url: %s", actual_url)
        return 1.0 if compare_urls(expected_url, actual_url) else 0.0
    else:
        logger.error("Unknown type: %s", match_type)
        return 0.0


def is_expected_active_tab_approximate(
    active_tab_info: Dict[str, str], rule: Dict[str, Any]
) -> float:
    """Check if the expected active tab is open, ignoring query parameters."""
    if not active_tab_info:
        return 0.0

    match_type = rule["type"]
    if match_type == "url":
        from urllib.parse import urlparse, urlunparse

        expected_url = rule["url"]
        actual_url = (
            active_tab_info.get("url", None) if isinstance(active_tab_info, dict) else active_tab_info
        )

        def strip_query(url):
            parsed = urlparse(url)
            return urlunparse(parsed._replace(query=""))

        return 1.0 if strip_query(expected_url) == strip_query(actual_url) else 0.0
    else:
        logger.error("Unknown type: %s", match_type)
        return 0.0


def is_expected_url_pattern_match(result, rules) -> float:
    """Search for expected regex patterns in the URL."""
    if not result:
        return 0.0

    if isinstance(result, str):
        result_url = result
    elif isinstance(result, dict) and "url" in result:
        result_url = result["url"]
    else:
        logger.error("Invalid result format: %s", type(result))
        return 0.0

    patterns = rules["expected"]
    for pattern in patterns:
        if not re.search(pattern, result_url):
            return 0.0
    return 1.0


def is_expected_installed_extensions(installed_extensions, expected) -> float:
    """Check if expected Chrome extensions are installed."""
    if not installed_extensions:
        return 0.0

    expected_extensions = set(expected["expected"])
    actual_extensions = set(installed_extensions)
    return 1.0 if expected_extensions.issubset(actual_extensions) else 0.0


def is_expected_tabs(open_tabs: List[Dict[str, str]], rule: Dict[str, Any]) -> float:
    """Check if the expected tabs are open in Chrome."""
    if not open_tabs:
        return 0.0

    match_type = rule["type"]
    if match_type == "url":
        expected_urls = rule["urls"]
        actual_urls = [tab["url"] for tab in open_tabs]
        return 1.0 if are_lists_equal(expected_urls, actual_urls, compare_urls) else 0.0
    else:
        logger.error("Unknown type: %s", match_type)
        return 0.0


def is_expected_bookmarks(bookmarks, rule: Dict[str, Any]) -> float:
    """Check if expected bookmarks are in Chrome."""
    if not bookmarks:
        return 0.0

    if rule["type"] == "bookmark_bar_folders_names":
        folder_names = [
            bm["name"]
            for bm in bookmarks["bookmark_bar"]["children"]
            if bm["type"] == "folder"
        ]
        return 1.0 if set(folder_names) == set(rule["names"]) else 0.0

    elif rule["type"] == "bookmark_bar_websites_urls":
        urls = [
            bm["url"]
            for bm in bookmarks["bookmark_bar"]["children"]
            if bm["type"] == "url"
        ]
        return 1.0 if set(urls) == set(rule["urls"]) else 0.0

    elif rule["type"] == "liked_authors_websites_urls":
        liked_folder = next(
            (
                bm
                for bm in bookmarks["bookmark_bar"]["children"]
                if bm["type"] == "folder" and bm["name"] == "Liked Authors"
            ),
            None,
        )
        if not liked_folder:
            return 0.0
        liked_urls = [
            bm["url"] for bm in liked_folder["children"] if bm["type"] == "url"
        ]
        urls = rule["urls"]
        for idx, url in enumerate(urls):
            if isinstance(url, str):
                urls[idx] = [url]
        for combination in product(*urls):
            if set(combination) == set(liked_urls):
                return 1.0
        return 0.0

    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def is_expected_search_query(active_tab_info: Dict[str, str], rules: Dict[str, Any]) -> float:
    """Check if the expected search query is in the active tab URL."""
    if not active_tab_info:
        return 0.0

    expected = rules["expect"]
    pattern = expected["pattern"]
    return 1.0 if re.search(pattern, active_tab_info["url"]) else 0.0


def compare_pdfs(
    pdf1_path: Union[str, List[str]], pdf2_path: Union[str, List[str]]
) -> float:
    """Compare two PDF files by text content using fuzzy matching."""
    if not isinstance(pdf2_path, list):
        pdf1_path, pdf2_path = [pdf1_path], [pdf2_path]

    def extract_text(path: str) -> str:
        text = ""
        with fitz.open(path) as pdf:
            for page in pdf:
                text += page.get_text()
        return text.strip()

    score = 0.0
    for p1, p2 in zip(pdf1_path, pdf2_path):
        try:
            score += fuzz.ratio(extract_text(p1), extract_text(p2)) / 100
        except Exception as e:
            logger.error("Error comparing PDFs: %s", e)
    return score / len(pdf2_path)


def compare_pdf_images(pdf1_path: str, pdf2_path: str, **kwargs) -> float:
    """Compare images extracted from two PDF files using perceptual hashing."""
    if not pdf1_path or not pdf2_path:
        return 0.0
    if not all(map(os.path.exists, [pdf1_path, pdf2_path])):
        logger.warning("PDF file does not exist: %s or %s", pdf1_path, pdf2_path)
        return 0.0

    def extract_images(path: str) -> List[Image.Image]:
        doc = fitz.open(path)
        images = []
        for page_num in range(doc.page_count):
            page = doc[page_num]
            for img in page.get_images(full=True):
                xref = img[0]
                base_image = doc.extract_image(xref)
                try:
                    pil_image = Image.open(io.BytesIO(base_image["image"]))
                    images.append(pil_image)
                except Exception as e:
                    logger.error("Failed to process image on page %d: %s", page_num, e)
        return images

    from pathlib import Path

    temp_dir = Path(pdf1_path).parent / "temp_pdf_comparison"
    os.makedirs(temp_dir, exist_ok=True)
    shutil.copy(pdf1_path, temp_dir / Path(pdf1_path).name)
    shutil.copy(pdf2_path, temp_dir / Path(pdf2_path).name)

    try:
        images1 = extract_images(str(temp_dir / Path(pdf1_path).name))
        images2 = extract_images(str(temp_dir / Path(pdf2_path).name))
    except Exception as e:
        logger.error("Error extracting images from PDFs: %s", e)
        shutil.rmtree(temp_dir)
        return 0.0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if len(images1) != len(images2):
        logger.info("Different number of images: %d vs %d", len(images1), len(images2))
        return 0.0
    if not images1:
        return 1.0

    hash_threshold = 5
    total = 0
    for i, (img1, img2) in enumerate(zip(images1, images2)):
        h1 = imagehash.phash(img1)
        h2 = imagehash.phash(img2)
        diff = h1 - h2
        if diff <= hash_threshold:
            total += 1
    return total / len(images1)


def compare_archive(pred_path: str, gold_path: str, **kwargs) -> float:
    """Compare two archives by unpacking and comparing their contents."""
    file_path = kwargs.pop("file_path", "")

    if not pred_path:
        return 0.0

    pred_folder = os.path.splitext(pred_path)[0] + "_pred"
    gold_folder = os.path.splitext(gold_path)[0] + "_gold"

    if os.path.exists(pred_folder):
        shutil.rmtree(pred_folder, ignore_errors=True)
    os.makedirs(pred_folder)
    shutil.unpack_archive(pred_path, pred_folder)

    if not os.path.exists(gold_folder):
        os.makedirs(gold_folder)
        shutil.unpack_archive(gold_path, gold_folder)

    pred_files = sorted(os.listdir(os.path.join(pred_folder, file_path)))
    gold_files = sorted(os.listdir(os.path.join(gold_folder, file_path)))

    if pred_files != gold_files:
        return 0.0

    def get_compare_function():
        file_type = kwargs.pop("file_type", "text")
        compare_funcs = {
            "pdf": compare_pdfs,
        }
        if file_type in compare_funcs:
            return compare_funcs[file_type]
        # Lazy imports for cross-module references
        if file_type == "text":
            from .vscode import compare_text_file
            return compare_text_file
        elif file_type == "docx":
            from .docs import compare_docx_files
            return compare_docx_files
        elif file_type == "ppt":
            from .slides import compare_pptx_files
            return compare_pptx_files
        elif file_type == "image":
            from .vlc import compare_images
            return compare_images
        elif file_type == "csv":
            from .table import compare_csv
            return compare_csv
        elif file_type == "table":
            from .table import compare_table
            return compare_table
        elif file_type == "audio":
            from .vlc import compare_audios
            return compare_audios
        elif file_type == "video":
            from .vlc import compare_videos
            return compare_videos
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    compare_function = get_compare_function()
    score = 0.0
    for f1, f2 in zip(pred_files, gold_files):
        fp1 = os.path.join(pred_folder, file_path, f1)
        fp2 = os.path.join(gold_folder, file_path, f2)
        score += compare_function(fp1, fp2, **kwargs)
    return score / len(pred_files)


def compare_htmls(html_path1: str, html_path2: str, **options) -> float:
    """Compare two HTML files structurally."""
    with open(html_path1, "r", encoding="utf-8") as f:
        soup1 = BeautifulSoup(f, "lxml")
    with open(html_path2, "r", encoding="utf-8") as f:
        soup2 = BeautifulSoup(f, "lxml")

    ignore_sdnum = options.get("ignore_sdnum", None)

    def compare_elements(elem1, elem2):
        if not (isinstance(elem1, Tag) and isinstance(elem2, Tag)):
            return elem1 == elem2
        if elem1.name != elem2.name:
            return False
        if elem1.text.strip() != elem2.text.strip():
            return False
        if elem1.attrs != elem2.attrs:
            if ignore_sdnum:
                a1 = {k: v for k, v in elem1.attrs.items() if k != "sdnum"}
                a2 = {k: v for k, v in elem2.attrs.items() if k != "sdnum"}
                return a1 == a2
            return False
        return True

    for e1, e2 in zip(soup1.recursiveChildGenerator(), soup2.recursiveChildGenerator()):
        if not compare_elements(e1, e2):
            return 0.0
    return 1.0


def is_cookie_deleted(cookie_data, rule) -> float:
    """Check if cookies for specified domains are deleted."""
    if rule["type"] == "domains":
        cookie_domains = [cookie[1] for cookie in cookie_data]
        for domain in rule["domains"]:
            for cd in cookie_domains:
                if compare_urls(domain, cd):
                    return 0.0
        return 1.0
    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def is_shortcut_on_desktop(shortcuts: Dict[str, str], rule) -> float:
    """Check if a shortcut exists on the desktop."""
    if rule["type"] == "name":
        for _, content in shortcuts.items():
            if "Name=" + rule["name"] + "\n" in content:
                return 1.0
        return 0.0
    elif rule["type"] == "exec":
        for _, content in shortcuts.items():
            if "Exec=" + rule["exec"] + "\n" in content:
                return 1.0
        return 0.0
    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def check_history_deleted(history_data, rule) -> float:
    """Check if browsing history entries matching keywords are deleted."""
    if rule["type"] == "keywords":
        history_urls = [h[0] for h in history_data]
        for keyword in rule["keywords"]:
            for url in history_urls:
                if keyword in url:
                    return 0.0
        return 1.0
    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def check_enabled_experiments(enabled_experiments, rule) -> float:
    """Check if enabled Chrome experiments match expected values."""
    names = [exp.split("@")[0] for exp in enabled_experiments]
    if rule["type"] == "names":
        return 1.0 if names == rule["names"] else 0.0
    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def check_font_size(font_size, rule) -> float:
    """Check if Chrome font size matches expected value or range."""
    default = font_size["default_font_size"]
    if rule["type"] == "value":
        return 1.0 if default == rule["value"] else 0.0
    elif rule["type"] == "range":
        return 1.0 if rule["min"] < default < rule["max"] else 0.0
    else:
        raise TypeError(f"{rule['type']} not supported yet!")


def is_added_to_steam_cart(active_tab_info, rule) -> float:
    """Check if items are in the Steam cart by checking page content."""
    items = rule["items"]
    content = active_tab_info["content"]
    for item in items:
        if item not in content:
            return 0.0
    return 1.0

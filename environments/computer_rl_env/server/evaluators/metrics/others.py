import logging
import os
import os.path
import zipfile
from typing import Dict, List, Union

import lxml.html
from lxml.html import HtmlElement
from mutagen.easyid3 import EasyID3

from .general import diff_text_file
from .utils import _match_value_to_rule

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.others")


def process_epub(filename: str) -> List[str]:
    """Process an EPUB file by extracting and normalizing key files.

    Args:
        filename: Path to the EPUB file to process

    Returns:
        Sorted list of paths to extracted and processed files
    """
    file_list: List[str] = []

    base_dir: str = filename + ".dir"
    os.makedirs(base_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(filename, "r") as z_f:
            # Get list of all files in the zip archive
            zip_file_list = z_f.namelist()

            # Process toc.ncx if it exists
            if "toc.ncx" in zip_file_list:
                with (
                    z_f.open("toc.ncx") as in_f,
                    open(os.path.join(base_dir, "toc.ncx"), "w") as out_f,
                ):
                    contents: str = in_f.read().decode()
                    contents_lines = contents.splitlines()
                    for line in contents_lines:
                        if "navPoint" not in line:
                            out_f.write(line + "\n")
                file_list.append(os.path.join(base_dir, "toc.ncx"))
            else:
                logger.debug("toc.ncx not found in epub file: %s", filename)

            # Process content.opf if it exists
            if "content.opf" in zip_file_list:
                with (
                    z_f.open("content.opf") as in_f,
                    open(os.path.join(base_dir, "content.opf"), "w") as out_f,
                ):
                    contents: str = in_f.read().decode()
                    contents_lines = contents.splitlines()
                    for line in contents_lines:
                        if "dc:identifier" not in line:
                            out_f.write(line + "\n")
                file_list.append(os.path.join(base_dir, "content.opf"))
            else:
                logger.debug("content.opf not found in epub file: %s", filename)

            # Process HTML files
            for f_n in z_f.namelist():
                if f_n.endswith(".html"):
                    with z_f.open(f_n) as in_f, open(os.path.join(base_dir, f_n), "w") as out_f:
                        html_content = in_f.read().decode()
                        filtered_content = "".join(
                            ch for ch in html_content if ch != "\n" and ch != "\r"
                        )
                        html: HtmlElement = lxml.html.fromstring(filtered_content.encode())
                        html_string = lxml.html.tostring(
                            html, pretty_print=True, encoding="unicode"
                        )
                        out_f.write(str(html_string))
                    file_list.append(os.path.join(base_dir, f_n))
        logger.debug("%s: %s", filename, file_list)
        return list(sorted(file_list))
    except zipfile.BadZipFile:
        return []


def compare_epub(result: str, expected: str) -> float:
    """Compare two EPUB files by processing and diffing their contents.

    Args:
        result: Path to the result EPUB file
        expected: Path to the expected EPUB file

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if result is None:
        return 0.0

    result_files: List[str] = process_epub(result)
    expected_files: List[str] = process_epub(expected)

    metric: float = 0.0
    for f1, f2 in zip(result_files, expected_files):
        current_metric: float = diff_text_file(f1, f2)
        logger.debug("%s vs %s: %f", f1, f2, current_metric)
        metric += current_metric
    if len(result_files) > 0:
        metric /= len(result_files)
    return metric


def check_mp3_meta(result: str, meta: Dict[str, Dict[str, Union[str, float, int]]]) -> float:
    """Check MP3 metadata against expected values.

    Args:
        result: Path to the MP3 file
        meta: Dictionary mapping metadata keys to rule dictionaries

    Returns:
        1.0 if all metadata matches, 0.0 otherwise
    """
    if result is None:
        return 0.0

    id3_dict = EasyID3(result)
    metric: bool = True
    for k, r in meta.items():
        value = id3_dict.get(k, "")
        if isinstance(value, list):
            value_str: str = ",".join(value)
        else:
            value_str = str(value)
        logger.debug("%s.%s: %s", result, k, value_str)
        metric = metric and _match_value_to_rule(value_str, r)
    return float(metric)

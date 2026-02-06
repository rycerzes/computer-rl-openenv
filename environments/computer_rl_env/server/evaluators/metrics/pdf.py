import logging
import operator
from typing import Any, Dict

import fitz  # pymupdf
from pypdf import PdfReader

logger = logging.getLogger("computer_rl_env.server.evaluators.metrics.pdf")


def check_pdf_pages(pdf_file: str, rules: Dict[str, Any]) -> float:
    if pdf_file is None:
        return 0.0
    reader = PdfReader(pdf_file)
    nb_pages: int = len(reader.pages)
    return float(getattr(operator, rules["relation"])(nb_pages, rules["ref_value"]))


def extract_answers_from_pdf(pdf_file):
    doc = fitz.open(pdf_file)
    answers = []

    for page in doc:
        text = page.get_text()
        if isinstance(text, str):
            lines = text.split("\n")
        else:
            lines = str(text).split("\n")
        for line in lines:
            if line.strip():
                parts = line.split("=")
                if len(parts) > 1:
                    answer = parts[-1].strip()
                    answers.append(answer)

    return answers

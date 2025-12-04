"""
Minimaler Keyword-Validator-Shim, damit die App ohne externe Module läuft.
Alle Keywords werden als gültig betrachtet; Strukturen bleiben kompatibel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any


@dataclass
class KeywordError:
    keyword: str
    error_type: str = "unknown"
    message: str = ""
    suggestion: str = ""


class ValidationResult:
    def __init__(self, invalid_keywords: List[KeywordError] | None = None):
        self.invalid_keywords = invalid_keywords or []


class KeywordValidator:
    def __init__(self, *args, **kwargs):
        pass

    def validate(self, keywords: List[str], task_type: str | None = None) -> ValidationResult:
        return ValidationResult([])


class APIEndpoint:
    def __init__(self, *args, **kwargs):
        pass


def validate_keywords_for_task_type(keywords: List[str], task_type: str | None = None) -> ValidationResult:
    # Akzeptiert alle Keywords als gültig
    return ValidationResult([])


def format_validation_report(validation_result: ValidationResult) -> str:
    if not validation_result.invalid_keywords:
        return "All keywords valid."
    return "\n".join(f"{err.keyword}: {err.message}" for err in validation_result.invalid_keywords)


def get_api_rules_summary() -> str:
    return "Keyword validation shim: no rules enforced."

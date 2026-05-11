"""Evidence descriptor inference from requirement and measure text.

Pattern-matches known evidence keywords against combined requirement +
measure text and returns a list of matched descriptor strings.
"""
from __future__ import annotations

import re
from typing import List


# (descriptor, compiled_pattern) — order doesn't matter; all are checked
_EVIDENCE_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    (
        "procedure",
        re.compile(
            r'\b(procedure|process|documented\s+process|written\s+procedure|'
            r'documented\s+method)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "screenshot",
        re.compile(
            r'\b(screenshot|screen\s+capture|screen\s+shot)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "report",
        re.compile(
            r'\b(report|summary\s+report|audit\s+report|assessment\s+report|'
            r'compliance\s+report)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "log",
        re.compile(
            r'\b(log|logs|event\s+log|audit\s+log|system\s+log|logging|'
            r'access\s+log|activity\s+log)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "approval_record",
        re.compile(
            r'\b(approv(?:al|ed|ing)|authoriz(?:ation|ed|ing)|'
            r'authorization\s+record)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "email",
        re.compile(
            r'\b(email|e-mail|electronic\s+mail|notification|'
            r'correspondence|communication)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "configuration_export",
        re.compile(
            r'\b(config(?:uration)?\s*(?:file|export|snapshot|backup|dump|record)|'
            r'settings\s+export|device\s+configuration)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "test_evidence",
        re.compile(
            r'\b(test(?:ing|ed|s)?|drill|exercise|validation|'
            r'verif(?:y|ied|ication)|functional\s+test|acceptance\s+test)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "submission_record",
        re.compile(
            r'\b(submit(?:ted|tal)?|submission|filing|filed|'
            r'report(?:ed|ing)\s+to|notif(?:y|ied)\s+(?:NERC|the\s+ERO))\b',
            re.IGNORECASE,
        ),
    ),
    (
        "signed_acknowledgement",
        re.compile(
            r'\b(sign(?:ed|ature|ing)|acknowledg(?:e|ment|ed|ing)|'
            r'attestation|attested|countersign)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "policy",
        re.compile(
            r'\b(policy|policies|directive|standard\s+operating|'
            r'security\s+plan|cyber\s+security\s+policy)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "diagram",
        re.compile(
            r'\b(diagram|network\s+diagram|topology|map|schematic|'
            r'drawing|logical\s+diagram|physical\s+diagram)\b',
            re.IGNORECASE,
        ),
    ),
    (
        "training_record",
        re.compile(
            r'\b(train(?:ing|ed|s)?|awareness\s+training|'
            r'training\s+record|certificate\s+of\s+(?:training|completion)|'
            r'security\s+awareness)\b',
            re.IGNORECASE,
        ),
    ),
]


def infer_evidence(requirement_text: str, measure_text: str = "") -> List[str]:
    """Infer expected evidence descriptors from requirement and measure text.

    Combines both texts and returns a deduplicated list of matched
    evidence descriptor strings from the controlled vocabulary:
    procedure, screenshot, report, log, approval_record, email,
    configuration_export, test_evidence, submission_record,
    signed_acknowledgement, policy, diagram, training_record.
    """
    combined = f"{requirement_text}\n{measure_text}"
    return [
        descriptor
        for descriptor, pattern in _EVIDENCE_PATTERNS
        if pattern.search(combined)
    ]

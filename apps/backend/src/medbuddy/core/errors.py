"""Domain exception hierarchy for MedBuddy.

Catches should target the most-specific class to avoid masking bugs.
All exceptions carry a human-readable ``message`` and an optional ``code``
that can be forwarded to API error responses.
"""

from __future__ import annotations


class Error(Exception):
    """Base for all application-level errors."""

    def __init__(self, message: str, *, code: str = "medbuddy_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigError(Error):
    """Raised when a required env var is missing or has an invalid value."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="config_error")


# ---------------------------------------------------------------------------
# LLM / AI layer
# ---------------------------------------------------------------------------


class LLMError(Error):
    """Raised when an LLM call fails (network, quota, parse error, etc.)."""

    def __init__(self, message: str, *, code: str = "llm_error") -> None:
        super().__init__(message, code=code)


class LLMParseError(LLMError):
    """The model returned a response that could not be parsed into the expected schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="llm_parse_error")


class LLMQuotaError(LLMError):
    """API quota / rate-limit exceeded."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="llm_quota_error")


# ---------------------------------------------------------------------------
# Agent layer
# ---------------------------------------------------------------------------


class AgentError(Error):
    """Raised when the agent cannot fulfil a request (tool failure, invalid state)."""

    def __init__(self, message: str, *, code: str = "agent_error") -> None:
        super().__init__(message, code=code)


class ToolExecutionError(AgentError):
    """A specific tool failed during execution."""

    def __init__(self, tool_name: str, cause: str) -> None:
        super().__init__(f"Tool '{tool_name}' failed: {cause}", code="tool_execution_error")
        self.tool_name = tool_name


# ---------------------------------------------------------------------------
# Medication / data layer
# ---------------------------------------------------------------------------


class MedicationError(Error):
    """Errors related to medication records."""

    def __init__(self, message: str, *, code: str = "medication_error") -> None:
        super().__init__(message, code=code)


class MedicationNotFoundError(MedicationError):
    """A referenced medication does not exist for the user."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Medication not found: {identifier}", code="medication_not_found")
        self.identifier = identifier


class MedicationExtractionError(MedicationError):
    """Could not extract a medication draft from the user's message."""

    def __init__(self) -> None:
        super().__init__(
            "Could not extract medication details from the message",
            code="medication_extraction_failed",
        )


class VitalExtractionError(Error):
    """Could not extract a usable vital sign reading from the user's message."""

    def __init__(self) -> None:
        super().__init__(
            "Could not extract vital sign details from the message",
            code="vital_extraction_failed",
        )


# ---------------------------------------------------------------------------
# Drug data layer
# ---------------------------------------------------------------------------


class DrugLookupError(Error):
    """Raised when a drug-data source (OpenFDA, TFDA) returns an error."""

    def __init__(self, source: str, cause: str) -> None:
        super().__init__(f"Drug lookup failed [{source}]: {cause}", code="drug_lookup_error")
        self.source = source


# ---------------------------------------------------------------------------
# Backward-compatible aliases (old module name was exceptions.py)
# ---------------------------------------------------------------------------

MedBuddyError = Error

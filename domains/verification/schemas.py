from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailVerifyRequest(BaseModel):
    """Batch email verification request payload.

    Enforces Invariant INV-BATCH-1:
    - Minimum 1 email address.
    - Maximum 25 email addresses per batch request.
    """

    emails: List[str] = Field(
        ...,
        description="List of email addresses to verify (1 to 25 emails).",
        min_length=1,
    )

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("emails")
    @classmethod
    def validate_batch_size_and_content(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Email batch cannot be empty.")

        count = len(v)
        if count > 25:
            # Enforce hard cap before any network call
            raise ValueError(f"Batch size of {count} exceeds maximum allowed limit of 25 emails.")

        cleaned_emails: List[str] = []
        for idx, email in enumerate(v):
            if not isinstance(email, str):
                raise ValueError(f"Email at index {idx} must be a string.")
            stripped = email.strip()
            if not stripped:
                raise ValueError(f"Email at index {idx} cannot be empty or whitespace.")
            cleaned_emails.append(stripped)

        return cleaned_emails


class EmailVerificationResult(BaseModel):
    """Compact, high-signal deliverability result designed for token efficiency in LLM agents."""

    email: str = Field(..., description="The verified email address.")
    classification: str = Field(
        ...,
        description="Deliverability classification: Deliverable, Undeliverable, Risky, Unknown, or Duplicate.",
    )
    status: str = Field(
        ...,
        description="Detailed Verifalia check status (e.g. Success, MailboxDoesNotExist, DisposableEmailAddress).",
    )
    is_deliverable: bool = Field(
        ...,
        description="True if the mailbox is definitely deliverable.",
    )
    is_disposable: bool = Field(
        default=False,
        description="True if the email domain is a temporary/disposable address provider.",
    )
    is_role_account: bool = Field(
        default=False,
        description="True if the email belongs to a role/generic account (e.g., support@, info@, billing@).",
    )
    is_free_email: bool = Field(
        default=False,
        description="True if the domain is a consumer free webmail provider (e.g. Gmail, Yahoo, Hotmail).",
    )

    model_config = ConfigDict(from_attributes=True)


class BatchVerificationResponse(BaseModel):
    """Aggregated response for a batch email verification request."""

    submitted: int = Field(..., description="Number of emails submitted in this batch.")
    completed: int = Field(..., description="Number of emails successfully evaluated.")
    cached: bool = Field(
        default=False,
        description="True if results were served directly from cache at 0 credit cost.",
    )
    results: List[EmailVerificationResult] = Field(
        ...,
        description="List of distilled verification outcomes.",
    )

    model_config = ConfigDict(from_attributes=True)


class CreditBalanceResponse(BaseModel):
    """Verifalia account credit balance and daily reset schedule."""

    credit_packs: float = Field(..., description="Available paid credit pack balance.")
    free_credits: float = Field(..., description="Available free daily credits (resets daily).")
    free_credits_reset_on: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp of next free credits reset (exact midnight 00:00:00 UTC).",
    )

    model_config = ConfigDict(from_attributes=True)

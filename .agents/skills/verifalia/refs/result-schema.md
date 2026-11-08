# Verifalia API: Validation Result Schema & Classification

## Overview

Each validated entry in the `entries` array contains a high-level `classification`, a fine-grained `status`, and granular diagnostic flags.

---

## 1. Classifications

Verifalia categorizes validated emails into 4 primary classifications:

| Classification | Meaning | Recommendation |
| :--- | :--- | :--- |
| **`Deliverable`** | Valid mailbox, accepting emails, no critical DNS/SMTP errors. | Safe to send. Low bounce risk. |
| **`Risky`** | Mailbox exists but has flags (e.g., catch-all domain, disposable provider, greylisting). | Send with caution; high likelihood of bounce or inactivity. |
| **`Undeliverable`** | Mailbox does not exist, syntax is broken, domain has no MX records, or server rejected recipient. | Do not send. Hard bounce guaranteed. |
| **`Unknown`** | Destination mail server timed out or was temporarily unreachable. | Retry later or treat as unverified. |

---

## 2. Granular Entry Properties

```json
{
  "index": 0,
  "inputData": "sales@temp-mail.org",
  "classification": "Risky",
  "status": "MailboxHasCompleted",
  "emailAddress": "sales@temp-mail.org",
  "emailAddressLocalPart": "sales",
  "emailAddressDomainPart": "temp-mail.org",
  "asciiEmailAddressDomainPart": "temp-mail.org",
  "hasInternationalMailboxName": false,
  "hasInternationalDomainName": false,
  "isDisposableEmailAddress": true,
  "isRoleAccount": true,
  "isFreeEmailAddress": false,
  "syntaxFailureIndex": null,
  "isSuccess": true,
  "isSyntaxFailure": false,
  "isDnsFailure": false,
  "isSmtpFailure": false,
  "isMailboxFailure": false,
  "isCatchAllFailure": false,
  "isTimeoutFailure": false,
  "isNetworkFailure": false
}
```

### Key Diagnostic Flags:
* `isDisposableEmailAddress` (boolean): `true` if the email provider is a disposable/throwaway domain (e.g. 10MinuteMail, TempMail).
* `isRoleAccount` (boolean): `true` if the mailbox is a role/generic account (e.g. `support@`, `info@`, `admin@`, `billing@`).
* `isFreeEmailAddress` (boolean): `true` for free consumer providers (Gmail, Yahoo, Hotmail, Outlook).
* `isSyntaxFailure` (boolean): Invalid RFC 5322 syntax.
* `isDnsFailure` (boolean): Domain has no MX or A records.
* `isSmtpFailure` (boolean): SMTP server connection or protocol failure.
* `isMailboxFailure` (boolean): Mailbox rejected or does not exist.
* `isCatchAllFailure` (boolean): Catch-all mailbox detected.

---

## 3. Compact Agent Representation (LLM-Friendly)

To prevent LLM context bloating, the application maps raw entries to this distilled structure:

```python
class EmailVerificationResult(BaseModel):
    email: str
    classification: str          # Deliverable | Undeliverable | Risky | Unknown
    status: str                  # Fine-grained status code
    is_deliverable: bool         # classification == "Deliverable"
    is_disposable: bool          # isDisposableEmailAddress
    is_role_account: bool        # isRoleAccount
    is_free_email: bool          # isFreeEmailAddress
```

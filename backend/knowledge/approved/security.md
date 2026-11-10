# Security, Backups & Compliance

## Data encryption

All data is encrypted in transit with TLS 1.3 and at rest with AES-256. Encryption keys are rotated automatically and are managed by our cloud provider's key management service.

Workspace owners can review the current sub-processor list at any time from the trust center.

## Backups

Backups run continuously with a 30-day retention window. Enterprise plans can enable daily exports to their own storage bucket, and point-in-time restore is available for the trailing 7 days.

Backups are encrypted with the same keys as live data and are restored only through a verified internal process with dual approval.

## GDPR & compliance

Workspace owners can file data export or deletion requests from Settings → Security; requests are acknowledged within 72 hours and completed within 30 days. A sub-processor list and our DPA are available in the trust center.

Deletion requests remove workspace content and member profiles. Invoices and records we must keep for tax purposes are retained in encrypted, access-restricted storage until the legal period expires.

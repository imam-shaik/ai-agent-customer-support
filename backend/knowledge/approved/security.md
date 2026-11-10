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

## Single sign-on (SSO)

Enterprise plans can connect a SAML 2.0 identity provider from Settings → Security. Once SSO is enforced, members authenticate through your identity provider and local credential entry is disabled for the workspace; invitations still control who may join — SSO governs how invited members authenticate, never who has access.

Provider metadata is entered by URL and tested with a single trial login before enforcement is switched on. Enforcing or disabling SSO is recorded in the audit log, and members keep their existing roles when the authentication method changes.

## Audit log

Enterprise workspaces can record security-relevant events — sign-ins, permission and settings changes, exports, and deletion requests — in an audit log kept for 12 months, viewable from Settings → Security → Audit log.

Every entry shows the actor, the event, and the timestamp in workspace time. The log can be exported as CSV, and entries age out automatically after 12 months; they are not part of the workspace JSON export described in the data-retention policy.

## Data residency

Workspace data is hosted in the EU or the US, chosen when the workspace is created, and the active region is shown in the trust center. Backups stay inside the same region as the workspace.

Moving an existing workspace to another region is a support request: the workspace is exported, re-created in the target region, and verified before the original copy is deleted under the standard deletion process.

## Reporting a security issue

Suspected vulnerabilities or incidents are reported through the contact in the trust center. Reports are acknowledged within 72 hours, and we ask for details privately rather than through public channels or tickets.

Reports never require sharing credentials or API keys — if a report includes a key, we treat it as compromised, revoke it, and ask you to re-issue it.

# Data Retention & Deletion Policy

## Retention periods

Active workspace data is retained while your subscription is paid and current. After the paid period ends, workspace data remains available in read-only mode for 30 days and is then permanently deleted, including conversations, tickets, and uploaded knowledge documents.

Backup copies age out on the rolling 30-day backup window, so no workspace content survives longer than 60 days after deletion.

## Deletion requests

Workspace owners can request immediate deletion from Settings → Security. Deletion is irreversible: conversations, tickets, and knowledge documents are removed and cannot be restored from the interface.

Deletion requests are acknowledged within 72 hours and completed within 30 days, matching the GDPR process described in the security documentation.

## Export your data

Before deleting anything, owners can export the workspace as JSON from Settings → Security. The export includes members, conversations with messages, tickets with events, and feedback.

The export link is valid for 24 hours and is sent only to the requesting owner's email address.

## Removed members

Removing a member from Settings → Team deactivates their access immediately, and their messages remain in the conversations they took part in. The member's profile is retained so re-adding the same person restores their account without duplicates, as described in the subscription guide.

Member removal is not deletion: the workspace's data, including the removed member's messages, follows the normal retention periods above.

## What the export contains

The JSON export contains members, conversations with their messages, tickets with their status events, and feedback records. It does not contain backups, audit-log entries, or embeddings — Enterprise audit logs are exported separately as CSV from the audit log screen.

Exports are generated on request and are not scheduled; if you need a recurring copy, Enterprise daily exports to your own storage bucket are the supported mechanism, as described in the security documentation.

## Restoring deleted data

Deletion is final in every direction: a deleted workspace cannot be restored from the interface, backups are never used to restore deleted workspace content on request, and a cancellation that completed its retention window cannot be reversed by re-subscribing.

The only reversible states are the ones before deletion — read-only access, pausing an annual plan, and cancelling before the window ends all keep data intact and restorable to full access.

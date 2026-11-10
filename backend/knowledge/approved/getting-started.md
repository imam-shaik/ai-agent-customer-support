# Getting Started with Northstar Desk

## Create your workspace

A workspace is created from your signup email and is owned by its creator. Roles are assigned per member: Admins manage billing and settings, Members work in conversations, and Viewers have read-only access. Owners can transfer ownership from Settings → Workspace.

Every workspace starts on a 14-day trial of the Pro plan. No payment method is required to run the trial, and conversations started during the trial stay in the workspace if you later downgrade.

## Invite your team

Workspace owners and admins can invite members from Settings → Team by email. Invite links expire after 7 days and can be resent or revoked at any time from the same screen.

When a member accepts, they choose their own password and sign in at the workspace URL shown in Settings → Workspace. Pending invitations do not consume a paid seat until the member accepts.

## Import your data

CSV and JSON imports run from Settings → Import. Files are validated before anything is written, and a dry-run report shows exactly what will be created so you can review it before confirming.

Large imports run in the background; you receive an email when the import finishes. If validation fails, no partial data is written — fix the file and run the import again.

```json
{ "workspace": "acme", "members": 12, "conversations": 430 }
```

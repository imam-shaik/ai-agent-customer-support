# Getting Started with Northstar Desk

## Create your workspace

A workspace is created from your signup email and is owned by its creator. Roles are assigned per member: Admins manage billing and settings, Members work in conversations, and Viewers have read-only access. Owners can transfer ownership from Settings → Workspace.

Every workspace starts on a 14-day trial of the Pro plan. No payment method is required to run the trial, and conversations started during the trial stay in the workspace if you later downgrade.

## Invite your team

Workspace owners and admins can invite teammates (members) from Settings → Team by email. Invite links expire after 7 days and can be resent or revoked at any time from the same screen.

When a member accepts, they choose their own password and sign in at the workspace URL shown in Settings → Workspace. Pending invitations do not consume a paid seat until the member accepts.

## Import your data

CSV and JSON imports run from Settings → Import. Files are validated before anything is written, and a dry-run report shows exactly what will be created so you can review it before confirming.

Large imports run in the background; you receive an email when the import finishes. If validation fails, no partial data is written — fix the file and run the import again.

```json
{ "workspace": "acme", "members": 12, "conversations": 430 }
```

## Roles & permissions

Owners have every permission, including transferring ownership and requesting workspace deletion. Admins manage billing, team members, integrations, and workspace settings, but cannot transfer ownership or delete the workspace. Members work in conversations — asking questions, raising tickets, and replying to their own threads. Viewers can read everything assigned to them but cannot send messages or change settings.

Permissions apply per member and take effect immediately when changed from Settings → Team. A member's role can be changed at any time, and removing a member deactivates their access on the spot while their past conversations remain in the workspace.

## Supported browsers

Northstar Desk runs in the two most recent major versions of Chrome, Edge, Firefox, and Safari on desktop, and in current Chrome and Safari on mobile. No installation or browser extension is needed — the workspace URL from Settings → Workspace is the only address required.

Older browsers can usually open the workspace, but unsupported versions are not tested and layout or delivery problems reported from them are fixed only in supported browsers.

## Your first conversation

Open the conversation panel, type a question, and the assistant answers from the approved help articles with citations you can open to inspect the exact evidence. Every answer names the documents it used; if the evidence is insufficient, the assistant says so instead of guessing and offers to create a ticket.

Raised tickets get an id like NSD-2026-4821, and the conversation up to that point is attached as context for the support team. You can keep asking questions in the same conversation and reference the ticket id at any time.

# Integrations & Notifications

## Slack integration

Connect Slack from Settings → Integrations, choose the channel for escalations and daily summaries, and approve the permission prompt. New tickets post to the channel within a minute of creation; connections can be paused without disconnecting.

Only workspace owners and admins can change the channel. Members can still read and reply to escalations in Slack if they have access to the channel.

## Email notifications

Per-member email preferences live in Settings → Notifications. Assignment, mention, and daily summary emails can be toggled independently, and a quiet window suppresses non-urgent mail overnight.

Transactional emails — password resets, security alerts, and billing receipts — are always sent and cannot be turned off.

## Webhooks

Outgoing webhooks deliver ticket and conversation events to your endpoint over HTTPS with a signing secret. Failed deliveries retry with backoff for up to 24 hours and appear in the delivery log.

```json
{
  "event": "ticket.created",
  "ticketId": "NSD-2026-4821",
  "status": "OPEN"
}
```

Endpoints must respond within 5 seconds. Events that keep failing after the retry window are marked failed in the delivery log and are not retried later.

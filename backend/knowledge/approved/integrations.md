# Integrations & Notifications

## Slack integration

Connect Slack from Settings → Integrations, choose the channel for escalations and daily summaries, and approve the permission prompt. New tickets post to the channel within a minute of creation; connections can be paused without disconnecting.

Only workspace owners and admins can change the channel. Members can still read and reply to escalations in Slack if they have access to the channel.

## Email notifications

Per-member email preferences live in Settings → Notifications. Assignment, mention, and daily summary emails can be toggled independently, and a quiet window suppresses non-urgent mail overnight.

Transactional emails — password resets, security alerts, and billing receipts — are always sent and cannot be turned off.

The daily summary is sent at 09:00 in the workspace timezone set in Settings → Workspace, so every member receives it at the same local time. The quiet window never delays transactional emails; it applies only to the notification types that can be toggled.

## Webhooks

Outgoing webhooks deliver ticket and conversation events to your endpoint over HTTPS with a signing secret, and delivery retries work automatically: failed deliveries retry with backoff for up to 24 hours and appear in the delivery log.

```json
{
  "event": "ticket.created",
  "ticketId": "NSD-2026-4821",
  "status": "OPEN"
}
```

Endpoints must respond within 5 seconds. Events that keep failing after the retry window are marked failed in the delivery log and are not retried later.

## Webhook events

Webhooks can subscribe to `ticket.created`, `ticket.status_changed`, and `conversation.escalated`; every payload uses the same envelope shown above with the event name and the affected record. Subscriptions are configured per endpoint from Settings → Integrations, and one endpoint can receive any combination of events.

The signing secret is shown once when the endpoint is created and can be rotated from the same screen — rotating a secret immediately applies to future deliveries while keeping the delivery log intact.

## API tokens

The REST API is available on Pro and Enterprise plans. Personal API tokens are created from Settings → Integrations → API tokens, are scoped either read-only or read-and-write, and act as the member who created them — a token can never exceed that member's permissions.

Rate limiting is 60 requests per minute per token, and the response headers report the remaining budget. There is no limit on the number of tokens, but each is shown only once at creation, so store it immediately; a lost token is revoked and replaced rather than recovered. Tokens can never change billing settings or workspace ownership.

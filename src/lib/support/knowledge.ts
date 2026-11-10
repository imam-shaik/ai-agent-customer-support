/**
 * Customer-workspace presentation vocabulary.
 *
 * Real knowledge lives in the backend only (`backend/knowledge/**` →
 * ingestion → pgvector retrieval → answer-time evidence snapshots).
 * This module holds no document content and no fallback corpus — only
 * the welcome screen's starter topics and the citation id shape shared
 * with the API client.
 */

export interface Citation {
  docId: string;
  sectionId: string;
}

/** Welcome-state topics with starter questions. */
export interface SupportTopic {
  id: string;
  label: string;
  description: string;
  questions: string[];
}

export const SUPPORT_TOPICS: SupportTopic[] = [
  {
    id: "account",
    label: "Account access",
    description: "Sign-in, passwords, recovery",
    questions: [
      "How do I reset my password?",
      "I'm locked out of my workspace",
      "How do I turn on two-factor authentication?",
    ],
  },
  {
    id: "billing",
    label: "Billing",
    description: "Invoices, charges, payment methods",
    questions: [
      "When am I billed?",
      "How do I update my payment method?",
      "I don't understand a charge on my invoice",
    ],
  },
  {
    id: "subscription",
    label: "Subscription management",
    description: "Plans, seats, upgrades",
    questions: [
      "How do I upgrade my plan?",
      "How do I add seats for my team?",
      "Can I pause my subscription?",
    ],
  },
  {
    id: "setup",
    label: "Product setup",
    description: "Team, imports, integrations",
    questions: [
      "How do I invite my team?",
      "How do I connect Slack?",
      "How do I import my data?",
    ],
  },
];

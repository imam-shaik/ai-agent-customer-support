import type { Metadata } from "next";
import { KnowledgeLibrary } from "@/components/domain/knowledge/knowledge-library";

export const metadata: Metadata = {
  title: "Knowledge base",
  description:
    "Synthetic Northstar Desk help documents, their processing status, and retrieval chunks.",
};

export default function KnowledgePage() {
  return <KnowledgeLibrary />;
}

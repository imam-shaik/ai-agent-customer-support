import { redirect } from "next/navigation";

/**
 * The knowledge base now lives inside the staff workspace as a tab
 * (/staff → "Knowledge base"). This route redirects so existing
 * links and bookmarks keep working.
 */
export default function KnowledgePage() {
  redirect("/staff");
}

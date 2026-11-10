import type { Metadata } from "next";
import { SupportStaffWorkspace } from "@/components/domain/staff/staff-workspace";

export const metadata: Metadata = {
  title: "Staff workspace",
  description:
    "Review AI escalations with full customer context for Northstar Desk support.",
};

export default function StaffPage() {
  return <SupportStaffWorkspace />;
}

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the Next.js dev-tools badge (the round "N" button that opens the
  // Route / Turbopack / Preferences popup). It is dev-only anyway —
  // production builds never show it — but a clean demo screen matters.
  devIndicators: false,
};

export default nextConfig;

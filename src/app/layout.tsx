import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { Providers } from "@/components/Providers";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Vilasat AI Support Intelligence",
    template: "%s · Vilasat AI",
  },
  description:
    "Grounded AI customer support with citations, honest fallbacks, and human escalation.",
};

export const viewport: Viewport = {
  themeColor: "#0d0e12",
  colorScheme: "dark light",
};

/**
 * Runs before first paint: applies the persisted theme (or the URL
 * ?theme= override for shareable themed links) to <html data-theme>,
 * so there is no flash of the wrong theme. Dark is the brand default.
 */
const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("vilasat.theme");if(t!=="light"&&t!=="dark"){t="dark"}var q=new URLSearchParams(location.search).get("theme");if(q==="light"||q==="dark"){t=q}document.documentElement.dataset.theme=t;var m=document.querySelector('meta[name="theme-color"]');if(m){m.setAttribute("content",t==="light"?"#f2f3f7":"#0d0e12")}}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable}`}
    >
      {/* suppressHydrationWarning on <body> (like <html>): browser
          extensions (Bing's bis_skin_checked/bis_register, Grammarly,
          translators…) mutate the DOM BEFORE React hydrates, which would
          otherwise flood dev with attribute-mismatch warnings that are
          not caused by application code. */}
      <body suppressHydrationWarning>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

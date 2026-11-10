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

/**
 * Runs before React hydrates: strips the attributes browser extensions
 * (Bing: bis_skin_checked / bis_register, Grammarly, translators, …)
 * stamp onto essentially every element. The extension mutates the DOM
 * BEFORE hydration, so React sees server HTML that the client tree
 * never produced and floods dev with hydration-mismatch errors that are
 * NOT caused by application code. Removing the injected attributes
 * pre-hydration re-aligns the server DOM with the client tree; the
 * MutationObserver closes the race where the extension re-injects while
 * hydration is still pending, and disconnects shortly after load
 * (post-hydration DOM mutations are React-visible events, not
 * hydration mismatches). Idempotent, app-attribute-safe (attribute
 * filter list only), and a no-op when no extension is present.
 */
const EXTENSION_ATTR_CLEANUP_SCRIPT = `(function(){try{var a=["bis_skin_checked","bis_register"];function c(){var n=document.querySelectorAll("[bis_skin_checked],[bis_register]");for(var i=0;i<n.length;i++){for(var j=0;j<a.length;j++){n[i].removeAttribute(a[j])}}}c();if(typeof MutationObserver==="undefined"){return}var o=new MutationObserver(function(){c()});o.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:a});window.addEventListener("load",function(){setTimeout(function(){o.disconnect()},5000)})}catch(e){}})();`;

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
        <script dangerouslySetInnerHTML={{ __html: EXTENSION_ATTR_CLEANUP_SCRIPT }} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

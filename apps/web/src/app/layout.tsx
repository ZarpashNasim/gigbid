import "./globals.css";
import type { ReactNode } from "react";
import HealthBanner from "@/components/HealthBanner";
import TokenGate from "@/components/TokenGate";

export const metadata = { title: "GigBid", description: "Multi-agent freelancer copilot" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en"><body>
      <HealthBanner />
      <nav aria-label="Main"><strong>GigBid</strong><a href="/">Inbox</a><a href="/messages">Messages</a></nav>
      <main><TokenGate>{children}</TokenGate></main>
    </body></html>
  );
}

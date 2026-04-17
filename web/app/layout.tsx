import "./globals.css";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import AuthGate from "@/components/AuthGate";
import BackgroundSquares from "@/components/BackgroundSquares";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Fanout — premium social drafts in seconds",
  description: "AI agents craft 5 platform-tailored drafts. You pick the winners. Posts ship via your own browser.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="font-sans">
        <BackgroundSquares />
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}

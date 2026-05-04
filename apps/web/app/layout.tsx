import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://demingroupmadrid.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "DEMIN Group — Demoliciones interiores en Madrid",
  description:
    "La fase cero de tu reforma. Demolición interior, vaciado de espacios y limpieza para constructoras, arquitectos y reformistas en Madrid.",
  keywords: [
    "demoliciones interiores Madrid",
    "demolición controlada",
    "vaciado de obra",
    "demolición selectiva",
    "preparación reforma",
  ],
  openGraph: {
    title: "DEMIN Group — Demoliciones interiores en Madrid",
    description: "La fase cero de tu reforma, sin contratiempos.",
    url: SITE_URL,
    siteName: "DEMIN Group",
    locale: "es_ES",
    type: "website",
    images: [{ url: "/og-image.jpg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "DEMIN Group — Demoliciones interiores en Madrid",
    description: "La fase cero de tu reforma, sin contratiempos.",
    images: ["/og-image.jpg"],
  },
  alternates: { canonical: SITE_URL },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={geistSans.variable}>
      <body className="antialiased">{children}</body>
    </html>
  );
}

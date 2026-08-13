import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Signal Council · 见微 | Evidence workbench",
  description: "De-identified finance-lease evidence workbench with advisory output and human gates.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

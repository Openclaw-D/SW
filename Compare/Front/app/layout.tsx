import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "signal-council | Evidence workbench",
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

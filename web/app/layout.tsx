import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Revere — Political Events Agent",
  description:
    "Structured political reasoning with auditable source and neutrality trace.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

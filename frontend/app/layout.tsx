import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SEC Management Change Tracker",
  description: "Tracks director/officer changes disclosed across SEC filers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

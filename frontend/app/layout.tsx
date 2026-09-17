import type { Metadata } from "next";
import Sidebar from "./Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "",
  description: "Tracks disclosures across SEC filers: management changes, SPAC IPOs, and 13F filings",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <Sidebar />
          <div className="app-content">{children}</div>
        </div>
      </body>
    </html>
  );
}

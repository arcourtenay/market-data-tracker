"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/13f-filings", label: "13F Filings" },
  { href: "/ipos", label: "IPOs" },
  { href: "/spac-ipos", label: "SPAC IPOs" },
  { href: "/director-share-buying", label: "Director Share Buying" },
  { href: "/financial-results", label: "Financial Results" },
  { href: "/companies-house-bidcos", label: "Companies House bidcos" },
  { href: "/takeover-panel-changes", label: "Takeover Panel changes" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="sidebar">
      <ul className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <li key={item.href}>
            <Link href={item.href} className={pathname === item.href ? "active" : undefined}>
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

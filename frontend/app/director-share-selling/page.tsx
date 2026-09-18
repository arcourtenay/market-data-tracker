"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { FILED_FROM_SHORTCUTS, isoDateAgo, todayIsoDate } from "@/lib/dateUtils";

type Company = {
  id: number;
  cik: string;
  name: string;
  ticker: string | null;
  sic: string | null;
  sic_description: string | null;
};

type DirectorSellEvent = {
  id: number;
  reporting_owner_name: string;
  officer_title: string | null;
  transaction_date: string;
  filing_date: string;
  shares: number;
  price_per_share: number;
  value_usd: number;
  filing_url: string;
  company: Company;
};

function formatUsd(value: number): string {
  return `$${Math.round(value).toLocaleString()}`;
}

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;
const DEFAULT_MIN_VALUE_MILLIONS = "0.1";

export default function DirectorShareSellingPage() {
  const [search, setSearch] = useState("");
  const [minValueMillions, setMinValueMillions] = useState(DEFAULT_MIN_VALUE_MILLIONS);
  const [filedFrom, setFiledFrom] = useState(() => isoDateAgo(DEFAULT_FILED_FROM_PERIOD));
  const [filedTo, setFiledTo] = useState(() => todayIsoDate());
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    search: "",
    minValueMillions: DEFAULT_MIN_VALUE_MILLIONS,
    filedFrom: isoDateAgo(DEFAULT_FILED_FROM_PERIOD),
    filedTo: todayIsoDate(),
  }));
  const [events, setEvents] = useState<DirectorSellEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    const params = new URLSearchParams();
    if (appliedFilters.search) params.set("search", appliedFilters.search);
    const minValue = Number(appliedFilters.minValueMillions);
    if (appliedFilters.minValueMillions !== "" && !Number.isNaN(minValue)) {
      params.set("min_value_usd", String(minValue * 1_000_000));
    }
    if (appliedFilters.filedFrom) params.set("filed_from", appliedFilters.filedFrom);
    if (appliedFilters.filedTo) params.set("filed_to", appliedFilters.filedTo);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/director-sells?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: DirectorSellEvent[]) => {
        if (!ignore) setEvents(data);
      })
      .catch((err) => {
        if (!ignore) setError(err.message || "Failed to load events");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [appliedFilters]);

  function applyFilters(e: React.FormEvent) {
    e.preventDefault();
    setAppliedFilters({ search, minValueMillions, filedFrom, filedTo });
  }

  return (
    <main>
      <h1>Director Share Selling</h1>
      <p className="subtitle">
        Open-market share sales by company directors, disclosed on Form 4 (transaction code &quot;S&quot;,
        disposed). Gifts, dispositions to the issuer, and tax withholding are excluded.
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Min $M sold
          <input
            type="number"
            min="0"
            step="any"
            value={minValueMillions}
            onChange={(e) => setMinValueMillions(e.target.value)}
          />
        </label>
        <label>
          Company / ticker / director
          <input
            type="text"
            placeholder="e.g. Acme, ACME, or Jane Smith"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Filed from
          <div className="filed-from-row">
            <input type="date" value={filedFrom} onChange={(e) => setFiledFrom(e.target.value)} />
            {FILED_FROM_SHORTCUTS.map((shortcut) => (
              <button
                key={shortcut.label}
                type="button"
                className={filedFrom === isoDateAgo(shortcut.period) ? "shortcut-btn active" : "shortcut-btn"}
                onClick={() => setFiledFrom(isoDateAgo(shortcut.period))}
              >
                {shortcut.label}
              </button>
            ))}
          </div>
        </label>
        <label>
          Filed to
          <div className="filed-to-row">
            <input type="date" value={filedTo} onChange={(e) => setFiledTo(e.target.value)} />
            <button
              type="button"
              className={filedTo === todayIsoDate() ? "shortcut-btn active" : "shortcut-btn"}
              onClick={() => setFiledTo(todayIsoDate())}
            >
              Today
            </button>
          </div>
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && !loading && events.length === 0 && (
        <div className="empty">No director sales match these filters.</div>
      )}

      {!error && (loading || events.length > 0) && (
        <div className="result-count">{loading ? "Loading…" : `${events.length} sale${events.length === 1 ? "" : "s"}`}</div>
      )}

      {!error && events.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Ticker</th>
                <th>Director</th>
                <th>Value ($)</th>
                <th>Filed</th>
                <th>Filing</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>{event.company.name}</td>
                  <td>{event.company.ticker || "—"}</td>
                  <td>
                    {event.reporting_owner_name}
                    {event.officer_title ? ` (${event.officer_title})` : ""}
                  </td>
                  <td>{formatUsd(event.value_usd)}</td>
                  <td>{event.filing_date}</td>
                  <td>
                    <a href={event.filing_url} target="_blank" rel="noreferrer">
                      View on SEC.gov
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

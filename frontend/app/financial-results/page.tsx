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
  market_cap_usd: number | null;
};

type FinancialResultEvent = {
  id: number;
  accession_no: string;
  form_type: string;
  filing_date: string;
  filing_url: string;
  company: Company;
};

function formatMarketCap(value: number | null): string {
  if (value === null) return "—";
  return `$${Math.round(value / 1_000_000).toLocaleString()}M`;
}

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;
const DEFAULT_MIN_MARKET_CAP_MILLIONS = "5000";

export default function FinancialResultsPage() {
  const [search, setSearch] = useState("");
  const [minMarketCapMillions, setMinMarketCapMillions] = useState(DEFAULT_MIN_MARKET_CAP_MILLIONS);
  const [filedFrom, setFiledFrom] = useState(() => isoDateAgo(DEFAULT_FILED_FROM_PERIOD));
  const [filedTo, setFiledTo] = useState(() => todayIsoDate());
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    search: "",
    minMarketCapMillions: DEFAULT_MIN_MARKET_CAP_MILLIONS,
    filedFrom: isoDateAgo(DEFAULT_FILED_FROM_PERIOD),
    filedTo: todayIsoDate(),
  }));
  const [events, setEvents] = useState<FinancialResultEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    const params = new URLSearchParams();
    if (appliedFilters.search) params.set("search", appliedFilters.search);
    const minCap = Number(appliedFilters.minMarketCapMillions);
    if (appliedFilters.minMarketCapMillions !== "" && !Number.isNaN(minCap)) {
      params.set("min_market_cap_millions", String(minCap));
    }
    if (appliedFilters.filedFrom) params.set("filed_from", appliedFilters.filedFrom);
    if (appliedFilters.filedTo) params.set("filed_to", appliedFilters.filedTo);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/financial-results?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: FinancialResultEvent[]) => {
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
    setAppliedFilters({ search, minMarketCapMillions, filedFrom, filedTo });
  }

  return (
    <main>
      <h1>Financial Results</h1>
      <p className="subtitle">
        Form 10-K and 10-Q filings (including amendments) across all SEC filers.
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Min market cap ($M)
          <input
            type="number"
            min="0"
            step="any"
            value={minMarketCapMillions}
            onChange={(e) => setMinMarketCapMillions(e.target.value)}
          />
        </label>
        <label>
          Company / ticker
          <input
            type="text"
            placeholder="e.g. Acme or ACME"
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
                className="shortcut-btn"
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
            <button type="button" className="shortcut-btn" onClick={() => setFiledTo(todayIsoDate())}>
              Today
            </button>
          </div>
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && !loading && events.length === 0 && (
        <div className="empty">No filings match these filters.</div>
      )}

      {!error && (loading || events.length > 0) && (
        <div className="result-count">{loading ? "Loading…" : `${events.length} filing${events.length === 1 ? "" : "s"}`}</div>
      )}

      {!error && events.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Ticker</th>
                <th>Market Cap</th>
                <th>Form</th>
                <th>Filed</th>
                <th>Filing</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>{event.company.name}</td>
                  <td>{event.company.ticker || "—"}</td>
                  <td>{formatMarketCap(event.company.market_cap_usd)}</td>
                  <td>{event.form_type}</td>
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

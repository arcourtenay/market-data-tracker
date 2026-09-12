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

type ManagementChangeEvent = {
  id: number;
  accession_no: string;
  form_type: string;
  items: string;
  filing_date: string;
  report_date: string | null;
  filing_url: string;
  company: Company;
};

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;
const DEFAULT_MIN_MARKET_CAP_MILLIONS = "5000";

export default function Home() {
  const [search, setSearch] = useState("");
  const [filedFrom, setFiledFrom] = useState(() => isoDateAgo(DEFAULT_FILED_FROM_PERIOD));
  const [filedTo, setFiledTo] = useState(() => todayIsoDate());
  const [minMarketCap, setMinMarketCap] = useState(DEFAULT_MIN_MARKET_CAP_MILLIONS);
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    search: "",
    filedFrom: isoDateAgo(DEFAULT_FILED_FROM_PERIOD),
    filedTo: todayIsoDate(),
    minMarketCap: DEFAULT_MIN_MARKET_CAP_MILLIONS,
  }));
  const [events, setEvents] = useState<ManagementChangeEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (appliedFilters.search) params.set("search", appliedFilters.search);
    if (appliedFilters.filedFrom) params.set("filed_from", appliedFilters.filedFrom);
    if (appliedFilters.filedTo) params.set("filed_to", appliedFilters.filedTo);
    if (appliedFilters.minMarketCap) params.set("min_market_cap_millions", appliedFilters.minMarketCap);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/events?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: ManagementChangeEvent[]) => setEvents(data))
      .catch((err) => setError(err.message || "Failed to load events"))
      .finally(() => setLoading(false));
  }, [appliedFilters]);

  function applyNow(overrides: Partial<typeof appliedFilters> = {}) {
    setAppliedFilters({ search, filedFrom, filedTo, minMarketCap, ...overrides });
  }

  function handleEnter(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      applyNow();
    }
  }

  return (
    <main>
      <h1>Management Changes</h1>
      <p className="subtitle">
        Director &amp; officer changes disclosed via Form 8-K, Item 5.02, across all SEC filers.
      </p>

      <div className="filters">
        <label>
          Min market cap ($M)
          <input
            type="number"
            min={0}
            step={100}
            placeholder="e.g. 5000"
            value={minMarketCap}
            onChange={(e) => setMinMarketCap(e.target.value)}
            onKeyDown={handleEnter}
          />
        </label>
        <label>
          Company / ticker
          <input
            type="text"
            placeholder="e.g. Apple or AAPL"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleEnter}
          />
        </label>
        <label>
          Filed from
          <div className="filed-from-row">
            <input
              type="date"
              value={filedFrom}
              onChange={(e) => {
                setFiledFrom(e.target.value);
                applyNow({ filedFrom: e.target.value });
              }}
            />
            {FILED_FROM_SHORTCUTS.map((shortcut) => (
              <button
                key={shortcut.label}
                type="button"
                className="shortcut-btn"
                onClick={() => {
                  const newDate = isoDateAgo(shortcut.period);
                  setFiledFrom(newDate);
                  applyNow({ filedFrom: newDate });
                }}
              >
                {shortcut.label}
              </button>
            ))}
          </div>
        </label>
        <label>
          Filed to
          <div className="filed-to-row">
            <input
              type="date"
              value={filedTo}
              onChange={(e) => {
                setFiledTo(e.target.value);
                applyNow({ filedTo: e.target.value });
              }}
            />
            <button
              type="button"
              className="shortcut-btn"
              onClick={() => {
                const newDate = todayIsoDate();
                setFiledTo(newDate);
                applyNow({ filedTo: newDate });
              }}
            >
              Today
            </button>
          </div>
        </label>
      </div>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && !loading && events.length === 0 && (
        <div className="empty">No management-change filings match these filters.</div>
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
              <th>Filed</th>
              <th>Filing</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td>{event.company.name}</td>
                <td>{event.company.ticker || "—"}</td>
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

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

type ActivistBuyEvent = {
  id: number;
  reporting_person_name: string;
  is_new_position: boolean;
  shares: number;
  price_per_share: number | null;
  value_usd: number | null;
  event_date: string;
  filing_date: string;
  filing_url: string;
  company: Company;
};

function formatUsd(value: number | null): string {
  if (value === null) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;
const DEFAULT_MIN_VALUE_MILLIONS = "0.1";

export default function ActivistShareBuyingPage() {
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
  const [events, setEvents] = useState<ActivistBuyEvent[]>([]);
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

    fetch(`${API_URL}/api/activist-buys?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: ActivistBuyEvent[]) => {
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
      <h1>Activist Share Buying</h1>
      <p className="subtitle">
        Increases in activist investors&apos; beneficial ownership, disclosed on Schedule 13D/13D-A: either a brand-new
        position or more shares than their last known position. Value ($) is a best-effort estimate (share price
        looked up near the filing date) since 13D reports a share count, not a transaction price.
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Min $M bought
          <input
            type="number"
            min="0"
            step="any"
            value={minValueMillions}
            onChange={(e) => setMinValueMillions(e.target.value)}
          />
        </label>
        <label>
          Company / ticker / activist
          <input
            type="text"
            placeholder="e.g. Acme, ACME, or Icahn"
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
            <button type="button" className="shortcut-btn" onClick={() => setFiledTo(todayIsoDate())}>
              Today
            </button>
          </div>
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && !loading && events.length === 0 && (
        <div className="empty">No activist purchases match these filters.</div>
      )}

      {!error && (loading || events.length > 0) && (
        <div className="result-count">{loading ? "Loading…" : `${events.length} purchase${events.length === 1 ? "" : "s"}`}</div>
      )}

      {!error && events.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Ticker</th>
                <th>Activist</th>
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
                    {event.reporting_person_name}
                    {event.is_new_position ? " (New position)" : ""}
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

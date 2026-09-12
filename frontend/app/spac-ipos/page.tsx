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

type SpacEvent = {
  id: number;
  accession_no: string;
  form_type: string;
  items: string;
  stage: "ipo" | "merger_completed";
  filing_date: string;
  report_date: string | null;
  filing_url: string;
  company: Company;
};

const STAGE_LABELS: Record<SpacEvent["stage"], string> = {
  ipo: "IPO",
  merger_completed: "Merger completed",
};

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;
const DEFAULT_MIN_MARKET_CAP_MILLIONS = "0";

export default function SpacIposPage() {
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState<"" | SpacEvent["stage"]>("");
  const [filedFrom, setFiledFrom] = useState(() => isoDateAgo(DEFAULT_FILED_FROM_PERIOD));
  const [filedTo, setFiledTo] = useState(() => todayIsoDate());
  const [minMarketCap, setMinMarketCap] = useState(DEFAULT_MIN_MARKET_CAP_MILLIONS);
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    search: "",
    stage: "" as "" | SpacEvent["stage"],
    filedFrom: isoDateAgo(DEFAULT_FILED_FROM_PERIOD),
    filedTo: todayIsoDate(),
    minMarketCap: DEFAULT_MIN_MARKET_CAP_MILLIONS,
  }));
  const [events, setEvents] = useState<SpacEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (appliedFilters.search) params.set("search", appliedFilters.search);
    if (appliedFilters.stage) params.set("stage", appliedFilters.stage);
    if (appliedFilters.filedFrom) params.set("filed_from", appliedFilters.filedFrom);
    if (appliedFilters.filedTo) params.set("filed_to", appliedFilters.filedTo);
    if (appliedFilters.minMarketCap) params.set("min_market_cap_millions", appliedFilters.minMarketCap);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/spac-events?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: SpacEvent[]) => setEvents(data))
      .catch((err) => setError(err.message || "Failed to load events"))
      .finally(() => setLoading(false));
  }, [appliedFilters]);

  function applyFilters(e: React.FormEvent) {
    e.preventDefault();
    setAppliedFilters({ search, stage, filedFrom, filedTo, minMarketCap });
  }

  return (
    <main>
      <h1>SPAC IPOs</h1>
      <p className="subtitle">
        SPAC lifecycle events across all SEC filers: new IPOs (Form 424B4, SIC 6770) and de-SPAC merger
        completions (Form 8-K, Item 5.06).
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Min market cap ($M)
          <input
            type="number"
            min={0}
            step={100}
            placeholder="e.g. 0"
            value={minMarketCap}
            onChange={(e) => setMinMarketCap(e.target.value)}
          />
        </label>
        <label>
          Company / ticker
          <input
            type="text"
            placeholder="e.g. Ajax or AJAX"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Stage
          <select value={stage} onChange={(e) => setStage(e.target.value as "" | SpacEvent["stage"])}>
            <option value="">All</option>
            <option value="ipo">IPO</option>
            <option value="merger_completed">Merger completed</option>
          </select>
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
        <div className="empty">No SPAC events match these filters.</div>
      )}

      {!error && (loading || events.length > 0) && (
        <div className="result-count">{loading ? "Loading…" : `${events.length} event${events.length === 1 ? "" : "s"}`}</div>
      )}

      {!error && events.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Ticker</th>
                <th>Stage</th>
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
                    <span className={`stage-tag stage-${event.stage}`}>{STAGE_LABELS[event.stage]}</span>
                  </td>
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

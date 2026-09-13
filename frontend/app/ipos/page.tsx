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
  ipo_proceeds_usd: number | null;
};

function formatIpoProceeds(value: number | null): string {
  if (value === null) return "—";
  return `$${Math.round(value / 1_000_000).toLocaleString()}M`;
}

type IpoEvent = {
  id: number;
  accession_no: string;
  form_type: string;
  stage: "s1_filed" | "priced";
  filing_date: string;
  report_date: string | null;
  filing_url: string;
  company: Company;
};

const STAGE_LABELS: Record<IpoEvent["stage"], string> = {
  s1_filed: "S-1 filed",
  priced: "Priced",
};

const DEFAULT_FILED_FROM_PERIOD = { months: 6 } as const;

export default function IposPage() {
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState<"" | IpoEvent["stage"]>("");
  const [filedFrom, setFiledFrom] = useState(() => isoDateAgo(DEFAULT_FILED_FROM_PERIOD));
  const [filedTo, setFiledTo] = useState(() => todayIsoDate());
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    search: "",
    stage: "" as "" | IpoEvent["stage"],
    filedFrom: isoDateAgo(DEFAULT_FILED_FROM_PERIOD),
    filedTo: todayIsoDate(),
  }));
  const [events, setEvents] = useState<IpoEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (appliedFilters.search) params.set("search", appliedFilters.search);
    if (appliedFilters.stage) params.set("stage", appliedFilters.stage);
    if (appliedFilters.filedFrom) params.set("filed_from", appliedFilters.filedFrom);
    if (appliedFilters.filedTo) params.set("filed_to", appliedFilters.filedTo);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/ipo-events?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data: IpoEvent[]) => setEvents(data))
      .catch((err) => setError(err.message || "Failed to load events"))
      .finally(() => setLoading(false));
  }, [appliedFilters]);

  function applyFilters(e: React.FormEvent) {
    e.preventDefault();
    setAppliedFilters({ search, stage, filedFrom, filedTo });
  }

  return (
    <main>
      <h1>IPOs</h1>
      <p className="subtitle">
        Non-SPAC IPOs across all SEC filers: companies that have filed a Form S-1 registration
        statement (&quot;S-1 filed&quot;, pre-IPO) or priced via Form 424B4 (&quot;Priced&quot;) - excluding
        SIC 6770 (SPACs).
      </p>

      <form className="filters" onSubmit={applyFilters}>
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
          Stage
          <select value={stage} onChange={(e) => setStage(e.target.value as "" | IpoEvent["stage"])}>
            <option value="">All</option>
            <option value="s1_filed">S-1 filed</option>
            <option value="priced">Priced</option>
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
        <div className="empty">No IPOs match these filters.</div>
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
                <th>IPO $M Raised</th>
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
                  <td>{formatIpoProceeds(event.company.ipo_proceeds_usd)}</td>
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

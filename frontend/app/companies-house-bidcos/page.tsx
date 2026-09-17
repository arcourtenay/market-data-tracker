"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { FILED_FROM_SHORTCUTS, isoDateAgo, todayIsoDate } from "@/lib/dateUtils";

type Bidco = {
  company_name: string;
  company_number: string;
  date_of_creation: string | null;
  company_status: string | null;
  locality: string | null;
  postal_code: string | null;
  country: string | null;
  incorporation_url: string;
};

const DEFAULT_NAME_INCLUDES = "BIDCO";
const DEFAULT_INCORPORATED_FROM_PERIOD = { months: 3 } as const;

function formatLocation(co: Bidco): string {
  const parts = [co.locality, co.postal_code, co.country].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "—";
}

export default function CompaniesHouseBidcosPage() {
  const [nameIncludes, setNameIncludes] = useState(DEFAULT_NAME_INCLUDES);
  const [incorporatedFrom, setIncorporatedFrom] = useState(() =>
    isoDateAgo(DEFAULT_INCORPORATED_FROM_PERIOD)
  );
  const [incorporatedTo, setIncorporatedTo] = useState(() => todayIsoDate());
  const [appliedFilters, setAppliedFilters] = useState(() => ({
    nameIncludes: DEFAULT_NAME_INCLUDES,
    incorporatedFrom: isoDateAgo(DEFAULT_INCORPORATED_FROM_PERIOD),
    incorporatedTo: todayIsoDate(),
  }));
  const [companies, setCompanies] = useState<Bidco[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    const params = new URLSearchParams();
    if (appliedFilters.nameIncludes) params.set("name_includes", appliedFilters.nameIncludes);
    if (appliedFilters.incorporatedFrom) params.set("incorporated_from", appliedFilters.incorporatedFrom);
    if (appliedFilters.incorporatedTo) params.set("incorporated_to", appliedFilters.incorporatedTo);

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/companies-house-bidcos?${params.toString()}`)
      .then(async (res) => {
        if (!res.ok) {
          const detail = await res.json().catch(() => null);
          throw new Error(detail?.detail || `API returned ${res.status}`);
        }
        return res.json();
      })
      .then((data: Bidco[]) => {
        if (!ignore) setCompanies(data);
      })
      .catch((err) => {
        if (!ignore) setError(err.message || "Failed to load companies");
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
    setAppliedFilters({ nameIncludes, incorporatedFrom, incorporatedTo });
  }

  return (
    <main>
      <h1>Companies House bidcos</h1>
      <p className="subtitle">
        UK companies incorporated with a keyword in their name (default &ldquo;BIDCO&rdquo;), pulled
        live from Companies House, newest first.
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Name includes
          <input
            type="text"
            placeholder="e.g. BIDCO"
            value={nameIncludes}
            onChange={(e) => setNameIncludes(e.target.value)}
          />
        </label>
        <label>
          Incorporated from
          <div className="filed-from-row">
            <input
              type="date"
              value={incorporatedFrom}
              onChange={(e) => setIncorporatedFrom(e.target.value)}
            />
            {FILED_FROM_SHORTCUTS.map((shortcut) => (
              <button
                key={shortcut.label}
                type="button"
                className="shortcut-btn"
                onClick={() => setIncorporatedFrom(isoDateAgo(shortcut.period))}
              >
                {shortcut.label}
              </button>
            ))}
          </div>
        </label>
        <label>
          Incorporated to
          <div className="filed-to-row">
            <input
              type="date"
              value={incorporatedTo}
              onChange={(e) => setIncorporatedTo(e.target.value)}
            />
            <button type="button" className="shortcut-btn" onClick={() => setIncorporatedTo(todayIsoDate())}>
              Today
            </button>
          </div>
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && !loading && companies.length === 0 && (
        <div className="empty">No companies match these filters.</div>
      )}

      {!error && (loading || companies.length > 0) && (
        <div className="result-count">
          {loading ? "Loading…" : `${companies.length} compan${companies.length === 1 ? "y" : "ies"}`}
        </div>
      )}

      {!error && companies.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Number</th>
                <th>Incorporated</th>
                <th>Status</th>
                <th>Location</th>
                <th>Incorporation doc</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((co) => (
                <tr key={co.company_number}>
                  <td>{co.company_name}</td>
                  <td>{co.company_number}</td>
                  <td>{co.date_of_creation || "—"}</td>
                  <td>{co.company_status || "—"}</td>
                  <td>{formatLocation(co)}</td>
                  <td>
                    {co.incorporation_url ? (
                      <a href={co.incorporation_url} target="_blank" rel="noreferrer">
                        View document
                      </a>
                    ) : (
                      "—"
                    )}
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

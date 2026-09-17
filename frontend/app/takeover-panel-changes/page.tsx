"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

type Entry = {
  offeree: string;
  offeree_lei: string | null;
  offer_period_commenced: string | null;
  offerors: string[];
  detail_lines: string[];
};

type Changes = {
  since_date: string | null;
  as_of: string;
  additions: Entry[];
  deletions: Entry[];
  current_count: number;
  baseline_count: number | null;
  note: string | null;
};

function EntryTable({ entries }: { entries: Entry[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Offeree</th>
            <th>Offeror(s)</th>
            <th>Offer period commenced</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.offeree}>
              <td>{e.offeree}</td>
              <td>{e.offerors.length > 0 ? e.offerors.join("; ") : "—"}</td>
              <td>{e.offer_period_commenced || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function TakeoverPanelChangesPage() {
  const [data, setData] = useState<Changes | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let ignore = false;
    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/takeover-panel-changes`)
      .then(async (res) => {
        if (!res.ok) {
          const detail = await res.json().catch(() => null);
          throw new Error(detail?.detail || `API returned ${res.status}`);
        }
        return res.json();
      })
      .then((json: Changes) => {
        if (!ignore) setData(json);
      })
      .catch((err) => {
        if (!ignore) setError(err.message || "Failed to load changes");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const hasChanges = data && (data.additions.length > 0 || data.deletions.length > 0);

  return (
    <main>
      <h1>Takeover Panel changes</h1>
      <p className="subtitle">
        Additions to and deletions from the UK Takeover Panel{" "}
        <a
          href="https://www.thetakeoverpanel.org.uk/disclosure/disclosure-table"
          target="_blank"
          rel="noreferrer"
        >
          disclosure table
        </a>
        , compared against the last snapshot taken on an earlier day.
      </p>

      <div className="result-count" style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button type="button" onClick={() => load()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        {data && !loading && (
          <span>
            {data.since_date
              ? `Changes since ${data.since_date} · ${data.current_count} offerees currently listed`
              : `${data.current_count} offerees currently listed`}
          </span>
        )}
      </div>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && data?.note && <div className="empty">{data.note}</div>}

      {!error && data && !data.note && !hasChanges && !loading && (
        <div className="empty">
          No additions or deletions since {data.since_date}.
        </div>
      )}

      {!error && data && !data.note && (
        <>
          {data.additions.length > 0 && (
            <section>
              <h2>New entries ({data.additions.length})</h2>
              <EntryTable entries={data.additions} />
            </section>
          )}
          {data.deletions.length > 0 && (
            <section>
              <h2>Deletions ({data.deletions.length})</h2>
              <EntryTable entries={data.deletions} />
            </section>
          )}
        </>
      )}
    </main>
  );
}

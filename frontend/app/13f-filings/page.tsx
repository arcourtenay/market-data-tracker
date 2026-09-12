"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

type Fund = {
  id: number;
  cik: string;
  name: string;
};

type FundHolding = {
  issuer_name: string;
  cusip: string;
  value_usd: number;
  shares: number;
  share_class: string | null;
  weight_pct: number;
};

type FundHoldingsResponse = {
  fund: Fund;
  period_of_report: string;
  filing_date: string;
  total_value_usd: number;
  holdings: FundHolding[];
};

function formatUsdMillions(value: number): string {
  return (value / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export default function ThirteenFFilingsPage() {
  const [funds, setFunds] = useState<Fund[]>([]);
  const [selectedFundId, setSelectedFundId] = useState<number | null>(null);
  const [data, setData] = useState<FundHoldingsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/funds`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((list: Fund[]) => {
        setFunds(list);
        if (list.length > 0) setSelectedFundId(list[0].id);
      })
      .catch((err) => setError(err.message || "Failed to load funds"));
  }, []);

  useEffect(() => {
    if (selectedFundId === null) return;

    setLoading(true);
    setError(null);
    setData(null);

    fetch(`${API_URL}/api/funds/${selectedFundId}/holdings`)
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "No holdings ingested yet for this fund" : `API returned ${res.status}`);
        return res.json();
      })
      .then((result: FundHoldingsResponse) => setData(result))
      .catch((err) => setError(err.message || "Failed to load holdings"))
      .finally(() => setLoading(false));
  }, [selectedFundId]);

  return (
    <main>
      <h1>13F Filings</h1>
      <p className="subtitle">
        Latest Form 13F-HR holdings disclosed by institutional managers, as % of total $M holdings disclosed.
      </p>

      <div className="filters">
        <label>
          Fund
          <select
            value={selectedFundId ?? ""}
            onChange={(e) => setSelectedFundId(Number(e.target.value))}
          >
            {funds.length === 0 && <option value="">No funds added yet</option>}
            {funds.map((fund) => (
              <option key={fund.id} value={fund.id}>
                {fund.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="error">Couldn&apos;t reach the API: {error}</div>}

      {!error && loading && <div className="result-count">Loading…</div>}

      {!error && !loading && data && (
        <>
          <div className="result-count">
            {data.holdings.length} holding{data.holdings.length === 1 ? "" : "s"} · as of {data.period_of_report} ·
            filed {data.filing_date} · total ${formatUsdMillions(data.total_value_usd)}M
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Issuer</th>
                  <th>CUSIP</th>
                  <th>Value ($M)</th>
                  <th>Shares</th>
                  <th>% of portfolio</th>
                </tr>
              </thead>
              <tbody>
                {data.holdings.map((holding, idx) => (
                  <tr key={`${holding.cusip}-${idx}`}>
                    <td>{holding.issuer_name}</td>
                    <td>{holding.cusip}</td>
                    <td>{formatUsdMillions(holding.value_usd)}</td>
                    <td>{holding.shares.toLocaleString()}</td>
                    <td>{holding.weight_pct.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

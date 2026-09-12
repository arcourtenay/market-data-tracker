export function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayIsoDate(): string {
  return toIsoDate(new Date());
}

export function isoDateAgo(period: { days?: number; months?: number; years?: number }): string {
  const date = new Date();
  if (period.days) date.setDate(date.getDate() - period.days);
  if (period.months) date.setMonth(date.getMonth() - period.months);
  if (period.years) date.setFullYear(date.getFullYear() - period.years);
  return toIsoDate(date);
}

export const FILED_FROM_SHORTCUTS: { label: string; period: Parameters<typeof isoDateAgo>[0] }[] = [
  { label: "1w", period: { days: 7 } },
  { label: "1m", period: { months: 1 } },
  { label: "6m", period: { months: 6 } },
  { label: "1y", period: { years: 1 } },
];

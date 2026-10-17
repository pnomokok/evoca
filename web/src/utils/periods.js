// Plain labels for the period enum (docs/api-samples/README.md: labels are the web client's job).
export const PERIOD_LABELS = {
  childhood: 'Childhood',
  youth: 'Youth',
  marriage_early_years: 'Early marriage',
  raising_children: 'Raising children',
  midlife: 'Midlife',
  retirement: 'Retirement'
};

export const PERIOD_ORDER = Object.keys(PERIOD_LABELS);

export function periodLabel(period) {
  return PERIOD_LABELS[period] || period || '';
}

// Years only come from the API (`years: {from, to}`); null when unknown.
export function periodYears(years) {
  if (!years || years.from == null) return '';
  return years.to == null ? `since ${years.from}` : `${years.from} – ${years.to}`;
}

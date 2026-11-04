import { describe, expect, it } from 'vitest';
import { formatAnalyticalValue, formatColumnHeader, isNumericColumn } from './table-domain';

describe('formatAnalyticalValue', () => {
  it('groups digits of numbers and of decimal text from the database', () => {
    // Match the user's locale (for example en-IN and en-US have different grouping).
    const format = new Intl.NumberFormat(undefined, { maximumFractionDigits: 20 });
    expect(formatAnalyticalValue(17080)).toBe(format.format(17080));
    expect(formatAnalyticalValue('17552267.65356')).toBe(format.format(17552267.65356));
    expect(formatAnalyticalValue('-1029962.20000')).toBe(format.format(-1029962.2));
  });

  it('leaves identifiers and other text untouched', () => {
    expect(formatAnalyticalValue('00702')).toBe('00702');
    expect(formatAnalyticalValue('75831563')).toBe('75831563');
    expect(formatAnalyticalValue('2026-10-12')).toBe('2026-10-12');
    expect(formatAnalyticalValue('v1.2.3')).toBe('v1.2.3');
  });

  it('formats missing, boolean and structured values', () => {
    expect(formatAnalyticalValue(null)).toBe('—');
    expect(formatAnalyticalValue(true)).toBe('True');
    expect(formatAnalyticalValue({ a: 1 })).toBe('{"a":1}');
  });
});

describe('isNumericColumn', () => {
  const rows = (...values: Array<string | number | null>) =>
    values.map((value, index) => ({ id: String(index), values: { v: value } }));

  it('treats numbers and decimal text as numeric but not identifiers', () => {
    expect(isNumericColumn(rows(1, 2.5, null), 'v')).toBe(true);
    expect(isNumericColumn(rows('10.5', '20.25'), 'v')).toBe(true);
    expect(isNumericColumn(rows('00702', '75831563'), 'v')).toBe(false);
    expect(isNumericColumn(rows(null, null), 'v')).toBe(false);
  });
});

describe('formatColumnHeader', () => {
  it('prefers custom column labels when supplied', () => {
    const custom = {
      total_expense: 'Total Expense',
      reason: 'Expense Category',
    };
    expect(formatColumnHeader('total_expense', custom)).toBe('Total Expense');
    expect(formatColumnHeader('reason', custom)).toBe('Expense Category');
  });

  it('formats snake_case column names to clean Title Case', () => {
    expect(formatColumnHeader('total_revenue')).toBe('Total Revenue');
    expect(formatColumnHeader('course_name')).toBe('Course Name');
    expect(formatColumnHeader('created_at')).toBe('Created At');
    expect(formatColumnHeader('is_active')).toBe('Is Active');
  });

  it('preserves uppercase for standard abbreviations (ID, URL, API, KPI, SQL, SKU)', () => {
    expect(formatColumnHeader('customer_id')).toBe('Customer ID');
    expect(formatColumnHeader('avatar_url')).toBe('Avatar URL');
    expect(formatColumnHeader('api_key')).toBe('API Key');
    expect(formatColumnHeader('kpi_score')).toBe('KPI Score');
  });

  it('handles camelCase column names', () => {
    expect(formatColumnHeader('totalRevenue')).toBe('Total Revenue');
    expect(formatColumnHeader('customerId')).toBe('Customer ID');
  });
});

import type { Report } from 'powerbi-client';
import type { ReportContext } from './api';

const FILTER_TYPES: Record<number, string> = {
  0: 'advanced',
  1: 'basic',
  2: 'unknown',
  3: 'include/exclude',
  4: 'relative date',
  5: 'Top N',
  6: 'tuple',
  7: 'relative time',
  9: 'hierarchy',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function columnTarget(value: unknown): value is { table: string; column: string } {
  return (
    isRecord(value) &&
    typeof value.table === 'string' &&
    value.table.length > 0 &&
    typeof value.column === 'string' &&
    value.column.length > 0 &&
    Object.keys(value).every((key) => ['table', 'column'].includes(key))
  );
}

function supportedValue(value: unknown): boolean {
  return (
    value === null ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value)) ||
    (typeof value === 'string' && value.length <= 4000)
  );
}

function supportedHierarchy(item: Record<string, unknown>): boolean {
  // A one-column hierarchy with explicit selected leaves is equivalent to an In filter.
  // Keep the SDK payload intact; the backend applies the same checks before compiling DAX.
  return (
    Array.isArray(item.target) &&
    item.target.length === 1 &&
    columnTarget(item.target[0]) &&
    Array.isArray(item.hierarchyData) &&
    item.hierarchyData.length > 0 &&
    item.hierarchyData.length <= 1000 &&
    item.hierarchyData.every(
      (node) =>
        isRecord(node) &&
        Object.keys(node).every((key) => ['operator', 'value', 'children'].includes(key)) &&
        node.operator === 'Selected' &&
        Object.hasOwn(node, 'value') &&
        supportedValue(node.value) &&
        (!Object.hasOwn(node, 'children') ||
          (Array.isArray(node.children) && node.children.length === 0)),
    )
  );
}

function filterIssue(filter: unknown, origin: string): string {
  if (!isRecord(filter)) return `${origin}: invalid filter`;
  const item = filter;
  const target = Array.isArray(item.target) ? item.target[0] : item.target;
  const field =
    isRecord(target) && typeof target.table === 'string' && typeof target.column === 'string'
      ? `${target.table}.${target.column}`
      : undefined;
  const label =
    typeof item.displayName === 'string' && item.displayName.trim()
      ? item.displayName.trim()
      : field;
  const location = label ? `${origin} (${label})` : origin;
  const type = typeof item.filterType === 'number' ? FILTER_TYPES[item.filterType] : undefined;
  if (item.filterType === 9)
    return `${location}: unsupported hierarchy selection (only explicit selections on one column are supported)`;
  if (!columnTarget(item.target))
    return `${location}: unsupported filter target${type ? ` (${type})` : ''}`;
  if (item.filterType === 0 || item.filterType === 1) {
    const operator = typeof item.operator === 'string' ? ` (${item.operator})` : '';
    return `${location}: unsupported ${type} filter or operator${operator}`;
  }
  return `${location}: unsupported ${type ?? 'unrecognized'} filter type`;
}

export function supportedFilter(filter: unknown): boolean {
  if (!isRecord(filter)) return false;
  const item = filter;
  if (item.filterType === 9) return supportedHierarchy(item);
  if (!columnTarget(item.target)) return false;
  if (item.filterType === 1)
    return (
      item.operator === 'All' ||
      (['In', 'NotIn'].includes(String(item.operator)) &&
        Array.isArray(item.values) &&
        item.values.length <= 1000 &&
        item.values.every(supportedValue))
    );
  if (item.filterType === 0)
    return (
      ['And', 'Or'].includes(
        String(item.logicalOperator === undefined ? 'And' : item.logicalOperator),
      ) &&
      Array.isArray(item.conditions) &&
      item.conditions.length <= 2 &&
      item.conditions.every(
        (condition) =>
          isRecord(condition) &&
          (['IsBlank', 'IsNotBlank'].includes(String(condition.operator)) ||
            ([
              'Is',
              'IsNot',
              'GreaterThan',
              'GreaterThanOrEqual',
              'LessThan',
              'LessThanOrEqual',
            ].includes(String(condition.operator)) &&
              supportedValue(condition.value === undefined ? null : condition.value))),
      )
    );
  return false;
}

export async function captureReportContext(
  report: Report,
  bindingId: string,
): Promise<ReportContext> {
  const page = await report.getActivePage();
  const filters: unknown[] = [];
  const unsupported: string[] = [];
  const addFilters = (items: unknown[], origin: string) => {
    for (const item of items) {
      filters.push(item);
      if (!supportedFilter(item)) unsupported.push(filterIssue(item, origin));
    }
  };
  addFilters(await report.getFilters(), 'Report filter');
  addFilters(await page.getFilters(), 'Page filter');
  const visuals = await page.getVisuals();
  for (const visual of visuals.filter((item) => item.type === 'slicer')) {
    try {
      addFilters((await visual.getSlicerState()).filters, `Slicer ${visual.title || visual.name}`);
    } catch {
      unsupported.push(`Slicer ${visual.title || visual.name} could not be read`);
    }
  }
  const currentPage = await report.getActivePage();
  if (currentPage.name !== page.name)
    throw new Error('The report page changed. Please send your question again.');
  return {
    report_binding_id: bindingId,
    page_name: page.name,
    page_display_name: page.displayName,
    mode: 'report_view',
    captured_at: new Date().toISOString(),
    filters: JSON.parse(JSON.stringify(filters)) as Record<string, unknown>[],
    unsupported,
  };
}

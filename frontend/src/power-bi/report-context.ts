import type { Report } from 'powerbi-client';
import type { ReportContext } from './api';

export function supportedFilter(filter: unknown): boolean {
  if (!filter || typeof filter !== 'object') return false;
  const item = filter as Record<string, unknown>;
  const target = item.target as Record<string, unknown> | undefined;
  if (
    !target ||
    typeof target.table !== 'string' ||
    typeof target.column !== 'string' ||
    Object.keys(target).some((key) => !['table', 'column'].includes(key))
  )
    return false;
  if (item.filterType === 1) return ['In', 'NotIn', 'All'].includes(String(item.operator));
  if (item.filterType === 0)
    return (
      ['And', 'Or'].includes(String(item.logicalOperator)) &&
      Array.isArray(item.conditions) &&
      item.conditions.length <= 2 &&
      item.conditions.every((condition: { operator?: string }) =>
        [
          'Is',
          'IsNot',
          'GreaterThan',
          'GreaterThanOrEqual',
          'LessThan',
          'LessThanOrEqual',
          'IsBlank',
          'IsNotBlank',
        ].includes(condition.operator ?? ''),
      )
    );
  return false;
}

export async function captureReportContext(
  report: Report,
  bindingId: string,
): Promise<ReportContext> {
  const page = await report.getActivePage();
  const filters = [...(await report.getFilters()), ...(await page.getFilters())];
  const unsupported: string[] = [];
  const visuals = await page.getVisuals();
  for (const visual of visuals.filter((item) => item.type === 'slicer')) {
    try {
      filters.push(...(await visual.getSlicerState()).filters);
    } catch {
      unsupported.push(`Slicer ${visual.title || visual.name} could not be read`);
    }
  }
  if (filters.some((filter) => !supportedFilter(filter)))
    unsupported.push('Some page filters or slicers are not supported');
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

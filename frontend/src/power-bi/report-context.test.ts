import { describe, expect, it } from 'vitest';
import type { Report } from 'powerbi-client';
import { captureReportContext, supportedFilter } from './report-context';

const filter = {
  filterType: 1,
  target: { table: 'Orders', column: 'Region' },
  operator: 'In',
  values: ['West'],
};
describe('Power BI report context', () => {
  it('accepts categorical filters and rejects unsupported relative-date/hierarchy filters', () => {
    expect(supportedFilter(filter)).toBe(true);
    expect(supportedFilter({ ...filter, filterType: 4 })).toBe(false);
    expect(supportedFilter({ ...filter, target: { table: 'Orders', hierarchy: 'Date' } })).toBe(
      false,
    );
  });
  it('captures report/page filters and slicers at send time', async () => {
    const page = {
      name: 'Page1',
      displayName: 'Backlog',
      getFilters: async () => [filter],
      getVisuals: async () => [
        { type: 'slicer', getSlicerState: async () => ({ filters: [filter] }) },
      ],
    };
    const report = {
      getActivePage: async () => page,
      getFilters: async () => [filter],
    } as unknown as Report;
    const snapshot = await captureReportContext(report, 'binding');
    expect(snapshot.filters).toHaveLength(3);
    expect(snapshot.page_display_name).toBe('Backlog');
    expect(snapshot.unsupported).toEqual([]);
  });
  it('records an unreadable slicer instead of silently ignoring its scope', async () => {
    const page = {
      name: 'Page1',
      displayName: 'Backlog',
      getFilters: async () => [],
      getVisuals: async () => [
        {
          type: 'slicer',
          name: 'Region',
          getSlicerState: async () => {
            throw new Error('unsupported');
          },
        },
      ],
    };
    const report = {
      getActivePage: async () => page,
      getFilters: async () => [],
    } as unknown as Report;
    expect((await captureReportContext(report, 'binding')).unsupported).toHaveLength(1);
  });
});

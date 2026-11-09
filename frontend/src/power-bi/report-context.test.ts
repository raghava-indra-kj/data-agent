import { describe, expect, it } from 'vitest';
import type { Report } from 'powerbi-client';
import { captureReportContext, supportedFilter } from './report-context';

const filter = {
  filterType: 1,
  target: { table: 'Orders', column: 'Region' },
  operator: 'In',
  values: ['West'],
};
const typeGroup = {
  $schema: 'http://powerbi.com/product/schema#hierarchy',
  filterType: 9,
  target: [{ table: 'Backlog_Main', column: 'TypeGroup' }],
  hierarchyData: [{ operator: 'Selected', value: 'Core' }],
};
const emptyWeek = {
  filterType: 0,
  target: { table: 'Backlog_Main', column: 'yCRDWeekNumber' },
  logicalOperator: 'And',
  conditions: [],
};
describe('Power BI report context', () => {
  it('accepts categorical filters and rejects unsupported relative-date/hierarchy filters', () => {
    expect(supportedFilter(filter)).toBe(true);
    expect(supportedFilter({ ...filter, filterType: 4 })).toBe(false);
    expect(supportedFilter({ ...filter, target: { table: 'Orders', hierarchy: 'Date' } })).toBe(
      false,
    );
  });
  it('accepts the single-column hierarchy returned by TypeGroup, including multiple selections and blanks', () => {
    expect(supportedFilter(typeGroup)).toBe(true);
    expect(
      supportedFilter({
        ...typeGroup,
        hierarchyData: [
          ...typeGroup.hierarchyData,
          { operator: 'Selected', value: 'Other', children: [] },
          { operator: 'Selected', value: null },
        ],
      }),
    ).toBe(true);
  });
  it.each([
    { ...typeGroup, target: [...typeGroup.target, { table: 'Backlog_Main', column: 'Region' }] },
    { ...typeGroup, target: [{ table: 'Backlog_Main', hierarchy: 'TypeGroup' }] },
    { ...typeGroup, hierarchyData: [{ operator: 'Inherited', value: 'Core' }] },
    { ...typeGroup, hierarchyData: [{ operator: 'NotSelected', value: 'Core' }] },
    { ...typeGroup, hierarchyData: [{ value: 'Core' }] },
    { ...typeGroup, hierarchyData: [{ operator: 'Selected' }] },
    { ...typeGroup, hierarchyData: [{ operator: 'Selected', value: 'Core', keyValues: ['id'] }] },
    {
      ...typeGroup,
      hierarchyData: [
        {
          operator: 'Selected',
          value: 'Core',
          children: [{ operator: 'NotSelected', value: 'Child' }],
        },
      ],
    },
    { ...typeGroup, hierarchyData: [{ operator: 'Selected', value: 'Core', children: null }] },
    { ...typeGroup, hierarchyData: [{ operator: 'Selected', value: {} }] },
    { ...typeGroup, hierarchyData: [] },
    { ...typeGroup, hierarchyData: [null] },
  ])('rejects hierarchy selections that cannot be reproduced safely (%#)', (item) => {
    expect(supportedFilter(item)).toBe(false);
  });
  it('accepts an unrestricted advanced filter but rejects malformed conditions and targets', () => {
    expect(supportedFilter(emptyWeek)).toBe(true);
    expect(supportedFilter({ ...emptyWeek, logicalOperator: 'Or' })).toBe(true);
    expect(supportedFilter({ ...emptyWeek, logicalOperator: undefined })).toBe(true);
    expect(supportedFilter({ ...emptyWeek, conditions: [null] })).toBe(false);
    expect(supportedFilter({ ...emptyWeek, conditions: null })).toBe(false);
    expect(supportedFilter({ ...emptyWeek, target: { table: 'Backlog_Main', column: '' } })).toBe(
      false,
    );
    expect(supportedFilter({ ...filter, values: [{}] })).toBe(false);
  });
  it('captures Stock Allocation selections without dropping filters or switching to entire model', async () => {
    const division = {
      ...filter,
      target: { table: 'Backlog_Main', column: 'New_div1' },
      values: ['BID'],
    };
    const status = {
      ...filter,
      target: { table: 'Backlog_Main', column: 'CRD_Status' },
      values: ['Current Quarter'],
    };
    const region = { ...filter, operator: 'NotIn', values: [null] };
    const page = {
      name: 'ReportSectionStockAllocation',
      displayName: 'Stock Allocation CTA',
      getFilters: async () => [emptyWeek, region],
      getVisuals: async () =>
        [typeGroup, division, status].map((item) => ({
          type: 'slicer',
          title: 'Slicer',
          getSlicerState: async () => ({ filters: [item] }),
        })),
    };
    const report = {
      getActivePage: async () => page,
      getFilters: async () => [],
    } as unknown as Report;
    const snapshot = await captureReportContext(report, 'binding');
    expect(snapshot.mode).toBe('report_view');
    expect(snapshot.page_display_name).toBe('Stock Allocation CTA');
    expect(snapshot.unsupported).toEqual([]);
    expect(snapshot.filters).toEqual([emptyWeek, region, typeGroup, division, status]);
    expect(snapshot.filters?.[2]).not.toBe(typeGroup);
  });
  it('names the field of an unsupported hierarchy without exposing selected values', async () => {
    const page = {
      name: 'Page1',
      displayName: 'Backlog',
      getFilters: async () => [],
      getVisuals: async () => [
        {
          type: 'slicer',
          title: 'Slicer',
          getSlicerState: async () => ({
            filters: [
              {
                ...typeGroup,
                hierarchyData: [{ operator: 'Inherited', value: 'private-value' }],
              },
            ],
          }),
        },
      ],
    };
    const report = {
      getActivePage: async () => page,
      getFilters: async () => [],
    } as unknown as Report;
    const snapshot = await captureReportContext(report, 'binding');
    expect(snapshot.unsupported?.[0]).toContain('Backlog_Main.TypeGroup');
    expect(snapshot.unsupported?.[0]).toContain('unsupported hierarchy selection');
    expect(snapshot.unsupported?.[0]).not.toContain('private-value');
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
    expect((await captureReportContext(report, 'binding')).unsupported).toEqual([
      'Slicer Region could not be read',
    ]);
  });
  it('identifies unsupported report filters and slicers without exposing selected values', async () => {
    const page = {
      name: 'Page1',
      displayName: 'Backlog',
      getFilters: async () => [{ ...filter, filterType: 4, values: ['private-value'] }],
      getVisuals: async () => [
        {
          type: 'slicer',
          name: 'visual-id',
          title: 'Date hierarchy',
          getSlicerState: async () => ({
            filters: [{ ...filter, target: { table: 'Orders', hierarchy: 'Date' } }],
          }),
        },
      ],
    };
    const report = {
      getActivePage: async () => page,
      getFilters: async () => [{ ...filter, filterType: 5 }],
    } as unknown as Report;
    const snapshot = await captureReportContext(report, 'binding');
    expect(snapshot.unsupported).toEqual([
      'Report filter (Orders.Region): unsupported Top N filter type',
      'Page filter (Orders.Region): unsupported relative date filter type',
      'Slicer Date hierarchy: unsupported filter target (basic)',
    ]);
    expect(snapshot.unsupported?.join(' ')).not.toContain('private-value');
  });
});

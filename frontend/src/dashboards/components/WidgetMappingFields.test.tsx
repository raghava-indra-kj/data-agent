import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { buildVisualizationConfig } from '../lib/widget-config';
import type { WidgetMappingValues, WidgetType } from '../schemas/dashboard-schemas';
import { WidgetMappingFields } from './WidgetMappingFields';

vi.mock('../../components/SingleSelect', () => ({
  SingleSelect: ({
    label,
    value,
    onChange,
    options,
  }: {
    label: string;
    value: string;
    onChange(value: string): void;
    options: Array<{ value: string; label: string }>;
  }) => (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  ),
}));

function Harness({ type = 'bar' }: { type?: WidgetType }) {
  const [values, setValues] = useState<WidgetMappingValues>({
    metricField: 'online',
    xField: 'category',
    categoryField: 'category',
    valueField: 'online',
    series: [{ field: 'online', label: 'Online sales' }],
  });
  return (
    <>
      <WidgetMappingFields
        widgetType={type}
        columns={['category', 'online', 'store', 'partner']}
        values={values}
        onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
      />
      <output data-testid="mapping">
        {JSON.stringify(buildVisualizationConfig({ ...values, widgetType: type }))}
      </output>
    </>
  );
}

it('keeps all selected components while changing orientation and stacking', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole('button', { name: 'Add series' }));
  await user.selectOptions(screen.getByLabelText('Orientation'), 'horizontal');
  await user.selectOptions(screen.getByLabelText('Series layout'), 'stacked');
  const mapping = JSON.parse(screen.getByTestId('mapping').textContent!);
  expect(mapping).toMatchObject({ orientation: 'horizontal', stacked: true });
  expect(mapping.series.map((item: { field: string }) => item.field)).toEqual(['online', 'store']);
  await user.selectOptions(screen.getByLabelText('Value field 2'), 'partner');
  expect(JSON.parse(screen.getByTestId('mapping').textContent!).series[1].field).toBe('partner');
  await user.click(screen.getByRole('button', { name: 'Remove series' }));
  expect(JSON.parse(screen.getByTestId('mapping').textContent!).series).toEqual([
    { field: 'online', label: 'Online sales' },
  ]);
});

it('edits a donut using category/value fields', async () => {
  const user = userEvent.setup();
  render(<Harness type="donut" />);
  expect(screen.queryByLabelText('Orientation')).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Value field'), 'store');
  expect(JSON.parse(screen.getByTestId('mapping').textContent!)).toEqual({
    category_field: 'category',
    value_field: 'store',
    value_label: 'store',
  });
});

it('assigns combo column and line roles, axes, units and axis titles', async () => {
  const user = userEvent.setup();
  render(<Harness type="combo" />);
  await user.click(screen.getByRole('button', { name: 'Add series' }));
  await user.selectOptions(screen.getByLabelText('Series 2 type'), 'line');
  await user.selectOptions(screen.getByLabelText('Series 2 axis'), 'secondary');
  await user.type(screen.getByLabelText('Series 1 unit'), 'count');
  await user.type(screen.getByLabelText('Series 2 unit'), '%');
  await user.type(screen.getByLabelText('Primary y-axis title'), 'Orders');
  await user.type(screen.getByLabelText('Secondary y-axis title'), 'Rate');
  await user.selectOptions(screen.getByLabelText('Series layout'), 'stacked');
  const mapping = JSON.parse(screen.getByTestId('mapping').textContent!);
  expect(mapping).toMatchObject({
    orientation: 'vertical',
    stacked: true,
    y_label: 'Orders',
    secondary_y_label: 'Rate',
    series: [
      { type: 'bar', axis: 'primary', unit: 'count' },
      { type: 'line', axis: 'secondary', unit: '%' },
    ],
  });
  expect(screen.queryByLabelText('Orientation')).not.toBeInTheDocument();
});

import type { JobArtifact, QueryExecution } from '../agent/api/execution-api';
import {
  MAX_METRIC_DETAILS,
  MAX_METRICS,
  METRIC_FORMATS,
  METRIC_ICONS,
  METRIC_POLARITIES,
  METRIC_TONES,
  toFiniteNumber,
  type MetricCardModel,
  type MetricDetailModel,
  type MetricFormat,
  type MetricIconName,
  type MetricPolarity,
  type MetricTone,
} from './metric-domain';

export type ChartType = 'bar' | 'line' | 'area' | 'pie' | 'donut' | 'metric' | 'combo';
export type CartesianChartType = Exclude<ChartType, 'pie' | 'donut' | 'metric'>;
export type ChartPoint = Record<string, string | number | null>;
export type AnalyticalSeries = {
  id: string;
  dataSourceId: string;
  dataSourceName: string;
  metric: string;
  label: string;
  unit?: string | null;
  type?: 'bar' | 'line';
  axis?: 'primary' | 'secondary';
  dimension: string;
  points: ChartPoint[];
};
export type MultiSourceChartModel = {
  id: string;
  title: string;
  chartType: CartesianChartType;
  orientation?: 'vertical' | 'horizontal';
  stacked?: boolean;
  yLabel?: string | null;
  secondaryYLabel?: string | null;
  dimension: string;
  dimensionLabel?: string | null;
  series: AnalyticalSeries[];
  provenance: Array<{
    dataSourceId: string;
    dataSourceName: string;
    executionId?: string;
    artifactId?: string;
  }>;
  comparisonKey?: string | null;
};
export type PieChartModel = {
  id: string;
  title: string;
  chartType: 'pie' | 'donut';
  category: string;
  value: string;
  valueLabel: string;
  unit?: string | null;
  dataSourceId: string;
  dataSourceName: string;
  points: ChartPoint[];
  provenance: MultiSourceChartModel['provenance'];
};
export type MetricChartModel = {
  id: string;
  title: string;
  chartType: 'metric';
  /** One to six cards; the first is the primary highlight. */
  metrics: MetricCardModel[];
  dataSourceId: string;
  dataSourceName: string;
  provenance: MultiSourceChartModel['provenance'];
};
/** Chart types rendered by AnalyticalChart — excludes the metric card. */
export type ChartableModel = MultiSourceChartModel | PieChartModel;
export type NormalizedChartModel = ChartableModel | MetricChartModel;

export function isCircularChart(model: NormalizedChartModel): model is PieChartModel {
  return model.chartType === 'pie' || model.chartType === 'donut';
}

function object(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}
const numeric = toFiniteNumber;

function oneOf<T extends string>(allowed: readonly T[], value: unknown, fallback: T): T | null {
  if (value === undefined || value === null) return fallback;
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null;
}

/** Parse the metric encoding into cards; null rejects the whole artifact. */
function parseMetricCards(
  encoding: Record<string, unknown>,
  data: unknown,
): MetricCardModel[] | null {
  const raw = Array.isArray(encoding.metrics) ? encoding.metrics.map(object) : null;
  if (!raw || raw.length < 1 || raw.length > MAX_METRICS || raw.some((item) => !item)) return null;
  const specs = raw as Record<string, unknown>[];
  const headlines = specs.map((item) => text(item.field));
  if (headlines.some((field) => !field) || new Set(headlines).size !== headlines.length)
    return null;
  const optionalFields = new Set<string>();
  const requiredFields = new Set<string>(headlines as string[]);
  for (const item of specs) {
    const comparisonField = text(item.comparison_field);
    if (item.comparison_field != null && !comparisonField) return null;
    if (comparisonField) optionalFields.add(comparisonField);
    if (item.details != null && !Array.isArray(item.details)) return null;
    for (const detail of (item.details as unknown[] | undefined) ?? []) {
      const detailField = text(object(detail)?.field);
      if (!detailField) return null;
      optionalFields.add(detailField);
    }
  }
  const chartPoints = points(data, new Set([...requiredFields, ...optionalFields]), optionalFields);
  if (!chartPoints || chartPoints.length !== 1) return null;
  const row = chartPoints[0]!;
  const cards: MetricCardModel[] = [];
  for (const item of specs) {
    const field = text(item.field)!;
    const format = oneOf<MetricFormat>(METRIC_FORMATS, item.format, 'number');
    const tone = oneOf<MetricTone>(METRIC_TONES, item.tone, 'neutral');
    const polarity = oneOf<MetricPolarity>(METRIC_POLARITIES, item.polarity, 'neutral');
    const icon =
      item.icon == null ? null : oneOf<MetricIconName>(METRIC_ICONS, item.icon, METRIC_ICONS[0]);
    if (!format || !tone || !polarity || (item.icon != null && !icon)) return null;
    const rawDetails = (item.details as unknown[] | undefined) ?? [];
    if (rawDetails.length > MAX_METRIC_DETAILS) return null;
    const details: MetricDetailModel[] = [];
    for (const rawDetail of rawDetails) {
      const detail = object(rawDetail)!;
      const detailField = text(detail.field)!;
      const detailFormat = oneOf<MetricFormat>(METRIC_FORMATS, detail.format, 'number');
      if (!detailFormat) return null;
      details.push({
        field: detailField,
        label: text(detail.label) ?? detailField,
        format: detailFormat,
        unit: text(detail.unit),
        value: numeric(row[detailField]),
      });
    }
    const comparisonField = text(item.comparison_field);
    const headline = numeric(row[field]);
    if (headline == null) return null;
    cards.push({
      field,
      label: text(item.label) ?? field,
      format,
      unit: text(item.unit),
      caption: text(item.caption),
      icon,
      tone,
      value: headline,
      comparison: comparisonField
        ? {
            field: comparisonField,
            label: text(item.comparison_label),
            value: numeric(row[comparisonField]),
          }
        : null,
      polarity,
      details,
    });
  }
  return cards;
}

function points(
  value: unknown,
  numericFields: Set<string>,
  nullableFields = new Set<string>(),
): ChartPoint[] | null {
  if (!Array.isArray(value)) return null;
  const result: ChartPoint[] = [];
  for (const raw of value) {
    const item = object(raw);
    if (!item) return null;
    const point: ChartPoint = {};
    for (const [key, cell] of Object.entries(item)) {
      if (cell == null || typeof cell === 'string' || typeof cell === 'number') {
        point[key] =
          numericFields.has(key) && cell != null ? numeric(cell) : (cell as string | number | null);
        if (numericFields.has(key) && cell != null && point[key] == null) return null;
      }
    }
    if (
      [...numericFields].some(
        (field) => !(field in point) || (point[field] == null && !nullableFields.has(field)),
      )
    )
      return null;
    result.push(point);
  }
  return result;
}

export function validComboSeries(
  series: Array<{ type?: unknown; axis?: unknown; unit?: unknown }>,
): boolean {
  if (!series.some((item) => item.type === 'bar') || !series.some((item) => item.type === 'line'))
    return false;
  if (
    series.some(
      (item) =>
        !['bar', 'line'].includes(String(item.type)) ||
        !['primary', 'secondary'].includes(String(item.axis ?? 'primary')) ||
        (item.type === 'bar' && item.axis === 'secondary'),
    )
  )
    return false;
  return ['primary', 'secondary'].every(
    (axis) =>
      new Set(
        series
          .filter((item) => (item.axis ?? 'primary') === axis)
          .map((item) => text(item.unit))
          .filter(Boolean),
      ).size <= 1,
  );
}

export function chartTypeLabel(type: ChartType, stacked = false): string {
  return type === 'combo'
    ? `Line + ${stacked ? 'stacked ' : ''}columns`
    : type[0]!.toUpperCase() + type.slice(1);
}

export function normalizeChartArtifact(
  artifact: JobArtifact,
  sql: QueryExecution | undefined,
  dataSourceName: string,
): NormalizedChartModel | null {
  const payload = object(artifact.payload);
  if (!payload || payload.schema_version !== 1 || payload.renderer !== 'frontend') return null;
  const payloadSqlId = text(payload.source_dax_execution_id ?? payload.source_sql_execution_id);
  const sourceExecutionId = artifact.source_dax_execution_id ?? artifact.source_sql_execution_id;
  if (
    payloadSqlId &&
    sourceExecutionId &&
    payloadSqlId !== sourceExecutionId
  )
    return null;
  const chartType = text(payload.chart_type) as ChartType | null;
  if (!chartType || !['bar', 'line', 'area', 'pie', 'donut', 'metric', 'combo'].includes(chartType))
    return null;
  if (
    payload.orientation !== undefined &&
    (typeof payload.orientation !== 'string' ||
      !['vertical', 'horizontal'].includes(payload.orientation))
  )
    return null;
  if (payload.stacked !== undefined && typeof payload.stacked !== 'boolean') return null;
  const orientation = payload.orientation === 'horizontal' ? 'horizontal' : 'vertical';
  const stacked = payload.stacked === true;
  if (!['bar', 'combo'].includes(chartType) && (orientation !== 'vertical' || stacked)) return null;
  if (chartType === 'combo' && orientation !== 'vertical') return null;
  if (chartType === 'combo' && sql && (sql.truncated || sql.status !== 'succeeded')) return null;
  const sourceId = sql?.data_source_id ?? text(payload.data_source_id) ?? 'datasource';
  const encoding = object(payload.encoding);
  if (!encoding) return null;
  const title = text(payload.title) ?? artifact.name ?? 'Chart';
  const provenance = [
    {
      dataSourceId: sourceId,
      dataSourceName: dataSourceName || 'Data source',
      executionId: sourceExecutionId ?? undefined,
      artifactId: artifact.id,
    },
  ];
  if (chartType === 'pie' || chartType === 'donut') {
    const category = object(encoding.category);
    const value = object(encoding.value);
    const categoryField = text(category?.field);
    const valueField = text(value?.field);
    if (!categoryField || !valueField) return null;
    const chartPoints = points(payload.data, new Set([valueField]));
    if (!chartPoints || chartPoints.some((point) => point[categoryField] == null)) return null;
    if (
      chartType === 'donut' &&
      (chartPoints.some((point) => Number(point[valueField]) < 0) ||
        !chartPoints.some((point) => Number(point[valueField]) > 0))
    )
      return null;
    const categoryValues = chartPoints.map((point) => String(point[categoryField]));
    if (new Set(categoryValues).size !== categoryValues.length) return null;
    return {
      id: artifact.id,
      title,
      chartType,
      category: categoryField,
      value: valueField,
      valueLabel: text(value?.label) ?? valueField,
      unit: text(value?.unit),
      dataSourceId: sourceId,
      dataSourceName: dataSourceName || 'Data source',
      points: chartPoints,
      provenance,
    };
  }
  if (chartType === 'metric') {
    const metrics = parseMetricCards(encoding, payload.data);
    if (!metrics) return null;
    return {
      id: artifact.id,
      title,
      chartType,
      metrics,
      dataSourceId: sourceId,
      dataSourceName: dataSourceName || 'Data source',
      provenance,
    };
  }
  const x = object(encoding.x);
  const xField = text(x?.field);
  const rawSeries = Array.isArray(encoding.series) ? encoding.series : null;
  if (!xField || !rawSeries?.length) return null;
  const seriesSpecs = rawSeries.map(object);
  if (seriesSpecs.length > 8 || seriesSpecs.some((item) => !item || !text(item.field))) return null;
  if (chartType === 'combo' && !validComboSeries(seriesSpecs as Record<string, unknown>[]))
    return null;
  const seriesFields = seriesSpecs.map((item) => text(item!.field)!);
  const numericFields = new Set(seriesFields);
  // Every series must represent a distinct measure. Labels are presentation-only and cannot
  // safely turn one repeated value field into separate category-filtered series.
  if (numericFields.size !== seriesFields.length || numericFields.has(xField)) return null;
  const units = [
    ...new Set(
      seriesSpecs.map((item) => text(item!.unit)).filter((unit): unit is string => Boolean(unit)),
    ),
  ];
  if (chartType !== 'combo' && (units.length > 2 || (stacked && units.length > 1))) return null;
  const nullableFields = new Set(
    chartType === 'combo'
      ? seriesSpecs
          .filter((item) => item!.type === 'line' || !stacked)
          .map((item) => text(item!.field)!)
      : [],
  );
  const chartPoints = points(payload.data, numericFields, nullableFields);
  if (!chartPoints || chartPoints.some((point) => point[xField] == null)) return null;
  if (
    chartType === 'combo' &&
    [...numericFields].some((field) => !chartPoints.some((point) => point[field] != null))
  )
    return null;
  const dimensionValues = chartPoints.map((point) => String(point[xField]));
  if (new Set(dimensionValues).size !== dimensionValues.length) return null;
  return {
    id: artifact.id,
    title,
    chartType,
    ...(['bar', 'combo'].includes(chartType) ? { orientation, stacked } : {}),
    ...(chartType === 'combo'
      ? { yLabel: text(payload.y_label), secondaryYLabel: text(payload.secondary_y_label) }
      : {}),
    dimension: xField,
    dimensionLabel: text(x?.label),
    comparisonKey: text(payload.comparison_key),
    series: seriesSpecs.map((item, index) => {
      const field = text(item!.field)!;
      return {
        id: `${artifact.id}:${field}:${index}`,
        dataSourceId: sourceId,
        dataSourceName: dataSourceName || 'Data source',
        metric: field,
        label: text(item!.label) ?? field,
        unit: text(item!.unit),
        ...(chartType === 'combo'
          ? {
              type: item!.type as 'bar' | 'line',
              axis: (item!.axis ?? 'primary') as 'primary' | 'secondary',
            }
          : {}),
        dimension: xField,
        points: chartPoints,
      };
    }),
    provenance,
  };
}

export function combineCompatibleCharts(models: NormalizedChartModel[]): NormalizedChartModel[] {
  const result: NormalizedChartModel[] = [];
  const grouped = new Map<string, MultiSourceChartModel[]>();
  for (const model of models) {
    if (
      isCircularChart(model) ||
      model.chartType === 'metric' ||
      model.chartType === 'combo' ||
      !model.comparisonKey
    ) {
      result.push(model);
      continue;
    }
    const units = [...new Set(model.series.map((series) => series.unit ?? 'unknown'))];
    if (units.includes('unknown') || units.length > 2) {
      result.push(model);
      continue;
    }
    const key = [
      model.comparisonKey,
      model.chartType,
      model.dimension,
      model.orientation ?? 'vertical',
      String(model.stacked ?? false),
      model.series.map((series) => series.metric).join('|'),
    ].join('::');
    grouped.set(key, [...(grouped.get(key) ?? []), model]);
  }
  for (const group of grouped.values()) {
    if (group.length < 2) {
      result.push(group[0]!);
      continue;
    }
    const units = [
      ...new Set(group.flatMap((item) => item.series.map((series) => series.unit ?? 'unknown'))),
    ];
    if (units.length > 2 || (group[0]!.stacked && units.length > 1)) {
      result.push(...group);
      continue;
    }
    result.push({
      ...group[0]!,
      id: group.map((item) => item.id).join('+'),
      series: group.flatMap((item) => item.series),
      provenance: group.flatMap((item) => item.provenance),
    });
  }
  return result;
}

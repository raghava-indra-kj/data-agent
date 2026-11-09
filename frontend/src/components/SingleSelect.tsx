import { Label, ListBox, Select } from '@heroui/react';
type Option<T extends string> = {
    value: T;
    label: string;
};
type Props<T extends string> = {
    label: string;
    value: T;
    onChange(value: T): void;
    options: readonly Option<T>[];
    disabled?: boolean;
    /** Inline control: no visible label (kept as aria-label), content-sized, short trigger. */
    compact?: boolean;
    className?: string;
};
export function SingleSelect<T extends string>({ label, value, onChange, options, disabled, compact, className }: Props<T>) {
    return <Select value={value} onChange={(next) => { if (typeof next === 'string')
        onChange(next as T); }} isDisabled={disabled} fullWidth={!compact} variant="secondary" className={className} aria-label={compact ? label : undefined}>
    {compact ? null : <Label>{label}</Label>}
    <Select.Trigger className={compact ? 'select-trigger--compact' : undefined}><Select.Value /><Select.Indicator /></Select.Trigger>
    <Select.Popover>
      <ListBox>{options.map((option) => <ListBox.Item id={option.value} key={option.value} textValue={option.label}><Label>{option.label}</Label></ListBox.Item>)}</ListBox>
    </Select.Popover>
  </Select>;
}

import { Button, Tooltip } from '@heroui/react';
import type { ComponentProps } from 'react';

/** Icon-only button whose label is both its accessible name and its hover/focus tooltip. */
export function TipButton({
  label,
  children,
  ...props
}: Omit<ComponentProps<typeof Button>, 'aria-label'> & { label: string }) {
  return (
    <Tooltip delay={350}>
      <Button isIconOnly size="sm" aria-label={label} {...props}>
        {children}
      </Button>
      <Tooltip.Content>{label}</Tooltip.Content>
    </Tooltip>
  );
}

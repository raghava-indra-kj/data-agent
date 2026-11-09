import { Button, Popover, Tooltip } from '@heroui/react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';

type Props = {
  label: string;
  tooltip: string;
  icon: ReactNode;
  isOpen: boolean;
  onOpenChange(open: boolean): void;
  disabled?: boolean;
  modified?: boolean;
  badgeCount?: number;
  wide?: boolean;
  placement?: 'top start' | 'top end';
  children: ReactNode;
};

/** Shared overlay behavior keeps the icon toolbar quiet and keyboard accessible. */
export function ComposerPopover({
  label,
  tooltip,
  icon,
  isOpen,
  onOpenChange,
  disabled,
  modified,
  badgeCount,
  wide,
  placement = 'top start',
  children,
}: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const descriptionId = useId();
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);
  const closeAndRestoreFocus = () => {
    onOpenChange(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!isOpen || !dialog) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      event.stopPropagation();
      onOpenChange(false);
      requestAnimationFrame(() => triggerRef.current?.focus());
    };
    dialog.addEventListener('keydown', handleEscape);
    return () => dialog.removeEventListener('keydown', handleEscape);
  }, [isOpen, onOpenChange]);
  return (
    <Popover isOpen={isOpen} onOpenChange={onOpenChange}>
      <Tooltip isOpen={tooltipOpen && !isOpen} onOpenChange={setTooltipOpen}>
        <Button
          ref={triggerRef}
          isIconOnly
          variant="ghost"
          size="sm"
          aria-label={label}
          aria-haspopup="dialog"
          aria-describedby={descriptionId}
          onHoverStart={() => setTooltipOpen(true)}
          onHoverEnd={() => setTooltipOpen(false)}
          onFocus={() => setTooltipOpen(true)}
          onBlur={() => setTooltipOpen(false)}
          isDisabled={disabled}
          className="composer-icon-button"
        >
          {icon}
          {badgeCount ? (
            <span className="composer-icon-count" aria-hidden="true">
              {badgeCount}
            </span>
          ) : modified && badgeCount === undefined ? (
            <span className="composer-icon-dot" aria-hidden="true" />
          ) : null}
        </Button>
        <Tooltip.Content triggerRef={triggerRef}>{tooltip}</Tooltip.Content>
      </Tooltip>
      <span id={descriptionId} className="sr-only">
        {badgeCount !== undefined
          ? `${badgeCount} data source${badgeCount === 1 ? '' : 's'} selected. `
          : ''}
        {tooltip}
      </span>
      <Popover.Content
        placement={placement}
        offset={10}
        isNonModal
        className={`composer-settings-popover ${wide ? 'composer-settings-popover--wide' : ''}`}
      >
        <Popover.Dialog ref={dialogRef} aria-label={label} className="composer-settings-dialog">
          <div className="composer-popover-layout">
            <div className="composer-popover-heading">
              <Popover.Heading>{wide ? 'Data sources' : label}</Popover.Heading>
              <Button
                isIconOnly
                size="sm"
                variant="ghost"
                aria-label={`Close ${label.toLowerCase()}`}
                onPress={closeAndRestoreFocus}
              >
                <X size={16} aria-hidden="true" />
              </Button>
            </div>
            {children}
          </div>
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}

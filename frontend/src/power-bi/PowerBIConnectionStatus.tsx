import { Button, Popover, Spinner } from '@heroui/react';
import { ChevronDown, CircleAlert, CircleCheck, X } from 'lucide-react';
import { useState } from 'react';
import { ConnectionPanel, usePowerBIConnection } from './ConnectionPanel';

export function PowerBIConnectionStatus() {
  const [open, setOpen] = useState(false);
  const { flags, connections } = usePowerBIConnection();
  const loading =
    flags.isPending ||
    (Boolean(flags.data?.enabled && flags.data?.configured) && connections.isPending);
  const unavailable = Boolean(flags.error || connections.error);
  const connected = connections.data?.[0]?.status === 'connected' && !unavailable;
  const label = loading
    ? 'Checking Power BI…'
    : unavailable
      ? 'Check Power BI connection'
      : connected
        ? 'Power BI connected'
        : 'Connect Power BI';

  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      <Button
        className="pbi-status-trigger"
        variant="ghost"
        size="sm"
        data-connected={connected}
        aria-label={`${label}. Manage Microsoft account`}
      >
        {loading ? (
          <Spinner size="sm" color="current" />
        ) : connected ? (
          <CircleCheck size={15} aria-hidden="true" />
        ) : (
          <CircleAlert size={15} aria-hidden="true" />
        )}
        <span>{label}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </Button>
      <Popover.Content placement="bottom start" className="pbi-account-popover">
        <Popover.Dialog aria-label="Microsoft account settings">
          <div className="pbi-account-popover-heading">
            <Popover.Heading>Power BI connection</Popover.Heading>
            <Button
              isIconOnly
              size="sm"
              variant="ghost"
              aria-label="Close Microsoft account settings"
              onPress={() => setOpen(false)}
            >
              <X size={16} aria-hidden="true" />
            </Button>
          </div>
          <ConnectionPanel />
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}

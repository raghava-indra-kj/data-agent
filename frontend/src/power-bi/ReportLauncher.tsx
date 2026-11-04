import { Button } from '@heroui/react';
import { useQuery } from '@tanstack/react-query';
import { ChartNoAxesCombined, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { ConnectionPanel, usePowerBIFeatures, usePowerBIIdentity } from './ConnectionPanel';
import * as api from './api';

export function ReportLauncher({
  sourceIds,
  onOpen,
}: {
  sourceIds: string[];
  onOpen(report: api.PowerBIReport): void;
}) {
  const identity = usePowerBIIdentity();
  const flags = usePowerBIFeatures();
  const [open, setOpen] = useState(false);
  const reports = useQuery({
    queryKey: ['power-bi', ...identity, 'reports', ...sourceIds],
    queryFn: async () => (await Promise.all(sourceIds.map(api.reports))).flat(),
    enabled: open && Boolean(flags.data?.enabled),
    retry: false,
    staleTime: 30_000,
  });
  return (
    <div className="pbi-launcher">
      <Button
        size="sm"
        variant="secondary"
        aria-expanded={open}
        onPress={() => setOpen((value) => !value)}
      >
        <ChartNoAxesCombined size={15} />
        Power BI
        <ChevronDown size={13} />
      </Button>
      {open && (
        <section className="pbi-launcher-menu" aria-label="Power BI reports">
          <ConnectionPanel />
          {reports.isPending && flags.data?.enabled && <p role="status">Checking report access…</p>}
          {reports.error && <p role="alert">{reports.error.message}</p>}
          {reports.data?.length === 0 && <p>No accessible reports are available.</p>}
          {reports.data?.map((report) => (
            <Button
              key={report.id}
              variant="tertiary"
              isDisabled={!flags.data?.embedding_enabled || !report.embedding_enabled}
              onPress={() => {
                onOpen(report);
                setOpen(false);
              }}
            >
              <ChartNoAxesCombined size={16} />
              {report.name}
            </Button>
          ))}
          {flags.data?.enabled && !flags.data.embedding_enabled && (
            <p>Report embedding is disabled. You can still ask questions about the model.</p>
          )}
        </section>
      )}
    </div>
  );
}

import { Button } from '@heroui/react';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { DataSource } from '../api/types';
import { ManagementHeader } from '../components/management/ManagementUI';
import { ConnectionPanel } from './ConnectionPanel';
import { PowerBICanvas } from './PowerBICanvas';
import { ReportLauncher } from './ReportLauncher';
import { refreshSource, type PowerBIReport } from './api';

export function PowerBIDetails({ source }: { source: DataSource }) {
  const [selected, setSelected] = useState<PowerBIReport | null>(null);
  const refresh = useMutation({ mutationFn: () => refreshSource(source.id) });
  return (
    <div className="conversation-with-report">
      <section className="management-page" style={{ flex: 1, minWidth: 300, overflow: 'auto' }}>
        <ManagementHeader
          title={source.name}
          backTo="/data-sources"
          backLabel="Back to data sources"
        >
          <ReportLauncher sourceIds={[source.id]} onOpen={setSelected} />
        </ManagementHeader>
        <section className="management-panel pbi-form">
          <h2>Power BI · Fabric IQ</h2>
          <p>
            Ask questions about this semantic model using your own Microsoft permissions. Reports
            open only when you select them from the Power BI menu.
          </p>
          <ConnectionPanel />
          <Button
            variant="secondary"
            isPending={refresh.isPending}
            onPress={() => refresh.mutate()}
          >
            Refresh access and metadata
          </Button>
          {refresh.isSuccess && (
            <p role="status">Your report access and model metadata have been refreshed.</p>
          )}
          {refresh.error && <p role="alert">{refresh.error.message}</p>}
          <Link to="/ask">Start a conversation</Link>
          <p>
            Select this source when asking a question. Power BI conversations and query results are
            private to you.
          </p>
          <Link to="/data-sources/new">Add another report</Link>
        </section>
      </section>
      {selected && (
        <PowerBICanvas
          key={selected.id}
          binding={selected}
          onClose={() => setSelected(null)}
          ref={null}
        />
      )}
    </div>
  );
}

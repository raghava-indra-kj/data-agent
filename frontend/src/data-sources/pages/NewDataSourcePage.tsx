import { Tabs } from '@heroui/react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { queryKeys } from '../../api/queryKeys';
import { ManagementHeader } from '../../components/management/ManagementUI';
import { PageState } from '../../components/PageState';
import { useJobManager } from '../../jobs/JobManagerProvider';
import { useOrganization } from '../../organizations/OrganizationProvider';
import * as api from '../api/data-source-api';
import { ExcelUploadForm } from '../components/ExcelUploadForm';
import { RelationalDataSourceForm } from '../components/RelationalDataSourceForm';
import { PowerBIForm } from '../../power-bi/PowerBIForm';
import { usePowerBIFeatures } from '../../power-bi/ConnectionPanel';

export function NewDataSourcePage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const { activeOrganization } = useOrganization();
  const jobs = useJobManager();
  const powerBI = usePowerBIFeatures();
  const [mode, setMode] = useState('database');
  const orgId = activeOrganization?.id ?? null;
  if (activeOrganization?.role !== 'owner' && activeOrganization?.role !== 'admin')
    return (
      <PageState
        title="Permission required"
        description="Only workspace owners and admins can add data sources."
      />
    );
  return (
    <section className="management-page management-form-page">
      <ManagementHeader
        title="Add data source"
        backTo="/data-sources"
        backLabel="Back to data sources"
      />
      <section className="management-panel">
        <Tabs
          className="management-tabs"
          variant="secondary"
          selectedKey={mode}
          onSelectionChange={(key) => setMode(String(key))}
        >
          <Tabs.ListContainer>
            <Tabs.List aria-label="Data source type">
              <Tabs.Tab id="database">
                Database
                <Tabs.Indicator />
              </Tabs.Tab>
              <Tabs.Tab id="excel">
                Excel workbook
                <Tabs.Indicator />
              </Tabs.Tab>
              {powerBI.data?.enabled && <Tabs.Tab id="powerbi">Power BI<Tabs.Indicator /></Tabs.Tab>}
            </Tabs.List>
          </Tabs.ListContainer>
          <Tabs.Panel id="database">
            <RelationalDataSourceForm
              onSubmit={async (payload) => {
                const source = await api.createRelationalDataSource(payload);
                await client.invalidateQueries({ queryKey: queryKeys.dataSources.all(orgId) });
                void navigate('/data-sources/' + source.id);
              }}
            />
          </Tabs.Panel>
          <Tabs.Panel id="excel">
            <ExcelUploadForm
              onSubmit={async (name, file) => {
                const result = await api.createExcelDataSource(name, file);
                await jobs.registerJob(result.job_id);
                await client.invalidateQueries({ queryKey: queryKeys.dataSources.all(orgId) });
                void navigate('/data-sources/' + result.data_source.id);
              }}
            />
          </Tabs.Panel>
          {powerBI.data?.enabled && <Tabs.Panel id="powerbi"><PowerBIForm onCreated={async (source) => {
            await client.invalidateQueries({ queryKey: queryKeys.dataSources.all(orgId) });
            void navigate('/data-sources/' + source.id);
          }} /></Tabs.Panel>}
        </Tabs>
      </section>
    </section>
  );
}

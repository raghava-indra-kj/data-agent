import { Button, Description, Input, InputGroup, Label, Spinner, TextField } from '@heroui/react';
import { useMutation } from '@tanstack/react-query';
import {
  ChartNoAxesCombined,
  ChevronRight,
  Link2,
  Search,
  SearchX,
  ShieldCheck,
} from 'lucide-react';
import { useRef, useState } from 'react';
import type { DataSource } from '../api/types';
import { ConnectionPanel, usePowerBIFeatures } from './ConnectionPanel';
import * as api from './api';

export function PowerBIForm({
  onCreated,
}: {
  onCreated(source: DataSource): Promise<void> | void;
}) {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [search, setSearch] = useState('');
  const [embed, setEmbed] = useState(true);
  const flags = usePowerBIFeatures();
  const reportLink = useRef<HTMLInputElement>(null);
  const lookup = useMutation({
    mutationFn: api.resolveReport,
    onSuccess: (report) => setName(report.name),
  });
  const discovery = useMutation({ mutationFn: api.discoverReports });
  const save = useMutation({
    mutationFn: () =>
      api.createSource({
        name,
        report_url: url,
        embedding_enabled: Boolean(flags.data?.embedding_enabled && embed),
      }),
    onSuccess: onCreated,
  });
  const error = lookup.error || discovery.error || save.error;
  const reports = discovery.data?.filter((report) => report.web_url) ?? [];
  return (
    <div className="pbi-form">
      <ConnectionPanel />
      <div className="pbi-report-intro">
        <h2>Choose a Power BI report</h2>
        <p>Search reports available to your Microsoft account, or paste a published report link.</p>
      </div>
      <form
        className="pbi-report-search"
        onSubmit={(event) => {
          event.preventDefault();
          if (search.trim() && !discovery.isPending) discovery.mutate(search.trim());
        }}
      >
        <TextField
          value={search}
          isDisabled={discovery.isPending}
          onChange={(value) => {
            setSearch(value);
            discovery.reset();
          }}
        >
          <Label>Find a report</Label>
          <div className="pbi-input-action">
            <InputGroup className="db-icon-search">
              <InputGroup.Prefix>
                <Search size={17} aria-hidden="true" />
              </InputGroup.Prefix>
              <InputGroup.Input
                className="db-icon-search__input"
                placeholder="Search by report name"
              />
            </InputGroup>
            <Button
              type="submit"
              variant="primary"
              isDisabled={!search.trim()}
              isPending={discovery.isPending}
            >
              {discovery.isPending ? (
                <Spinner size="sm" color="current" />
              ) : (
                <Search size={16} aria-hidden="true" />
              )}
              {discovery.isPending ? 'Searching…' : 'Search reports'}
            </Button>
          </div>
        </TextField>
        <div aria-live="polite" aria-busy={discovery.isPending}>
          {discovery.isSuccess &&
            (reports.length ? (
              <div className="pbi-search-results">
                <p className="pbi-result-count">
                  {reports.length} {reports.length === 1 ? 'report' : 'reports'} found · Select a
                  report to verify access
                </p>
                <ul className="pbi-report-list">
                  {reports.map((report) => (
                    <li key={report.web_url}>
                      <Button
                        className="pbi-report-result"
                        variant="ghost"
                        isDisabled={lookup.isPending || save.isPending}
                        onPress={() => {
                          setUrl(report.web_url!);
                          save.reset();
                          lookup.mutate(report.web_url!);
                        }}
                      >
                        <ChartNoAxesCombined size={18} aria-hidden="true" />
                        <span>{report.name}</span>
                        <ChevronRight size={16} aria-hidden="true" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="pbi-search-empty">
                <span className="pbi-search-empty-icon">
                  <SearchX size={24} aria-hidden="true" />
                </span>
                <h3>No reports found</h3>
                <p>
                  No reports match “{discovery.variables}”. Try a different name, or use a report
                  link.
                </p>
                <Button variant="outline" size="sm" onPress={() => reportLink.current?.focus()}>
                  <Link2 size={15} aria-hidden="true" />
                  Use a report link
                </Button>
              </div>
            ))}
        </div>
      </form>
      <div className="pbi-report-divider">
        <span>Or use a report link</span>
      </div>
      <form
        className="pbi-report-link-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (url.trim() && !lookup.isPending && !save.isPending) lookup.mutate(url.trim());
        }}
      >
        <TextField
          value={url}
          isDisabled={lookup.isPending || save.isPending}
          onChange={(value) => {
            setUrl(value);
            lookup.reset();
            save.reset();
          }}
        >
          <Label>Report link</Label>
          <div className="pbi-input-action">
            <InputGroup className="db-icon-search">
              <InputGroup.Prefix>
                <Link2 size={17} aria-hidden="true" />
              </InputGroup.Prefix>
              <InputGroup.Input
                className="db-icon-search__input"
                ref={reportLink}
                placeholder="https://app.powerbi.com/groups/…/reports/…"
              />
            </InputGroup>
            <Button
              type="submit"
              variant="outline"
              isDisabled={!url.trim() || save.isPending}
              isPending={lookup.isPending}
            >
              {lookup.isPending ? (
                <Spinner size="sm" color="current" />
              ) : (
                <ShieldCheck size={16} aria-hidden="true" />
              )}
              {lookup.isPending ? 'Verifying…' : 'Verify access'}
            </Button>
          </div>
          <Description>Open your report in Power BI and copy its browser URL.</Description>
        </TextField>
      </form>
      {lookup.data && (
        <form
          className="pbi-form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <p role="status">Verified: {lookup.data.name}</p>
          <TextField isRequired value={name} onChange={setName}>
            <Label>Data source name</Label>
            <Input maxLength={180} />
          </TextField>
          {flags.data?.embedding_enabled && (
            <label className="pbi-checkbox">
              <input
                type="checkbox"
                checked={embed}
                onChange={(event) => setEmbed(event.target.checked)}
              />
              Allow users to open this report alongside a conversation
            </label>
          )}
          <Button type="submit" isPending={save.isPending} isDisabled={!name.trim()}>
            Add Power BI source
          </Button>
        </form>
      )}
      {error && (
        <p role="alert" className="management-error">
          {error.message}
        </p>
      )}
    </div>
  );
}

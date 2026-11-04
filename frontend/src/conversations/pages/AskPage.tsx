import { useQuery } from '@tanstack/react-query';
import { PowerBIConnectionStatus } from '../../power-bi/PowerBIConnectionStatus';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { queryKeys } from '../../api/queryKeys';
import { useAuth } from '../../auth/AuthProvider';
import { BrandLogo } from '../../components/BrandLogo';
import { PageState } from '../../components/PageState';
import { listDataSources } from '../../data-sources/api/data-source-api';
import { preferences } from '../../lib/preferences';
import { listProfiles } from '../../models/api/models-api';
import { useOrganization } from '../../organizations/OrganizationProvider';
import * as api from '../api/conversation-api';
import { ChatComposer } from '../components/ChatComposer';
import { deriveConversationTitle } from '../utils/title';
import { normalizeTableScope } from '../components/table-scope';
import type { SourceTableScope } from '../components/table-scope';
import type { ReasoningEffort } from '../reasoning-effort';
import './ask-page.css';

type PendingConversationState = {
  pendingQuestion: string;
  modelProfileId: string | null;
  reasoningEffort: ReasoningEffort | null;
};

export function AskPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { activeOrganization } = useOrganization();
  const orgId = activeOrganization?.id ?? null;

  const dataSources = useQuery({
    queryKey: queryKeys.dataSources.list(orgId),
    queryFn: listDataSources,
    enabled: Boolean(orgId),
  });

  const profiles = useQuery({
    queryKey: queryKeys.models.profiles(orgId),
    queryFn: listProfiles,
    enabled: Boolean(orgId),
  });

  const [question, setQuestion] = useState('');
  const [tableSelections, setTableSelections] = useState<Record<string, SourceTableScope[]>>(() =>
    preferences.get('askTableSelectionsByScope') ?? {},
  );
  const sourceScope = JSON.stringify([user?.id, orgId]);
  const [sourceSelections, setSourceSelections] = useState<Record<string, string[]>>(() =>
    preferences.get('askDataSourceIdsByScope') ?? {},
  );
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(() => {
    return preferences.get('lastSelectedModelProfileId') ?? null;
  });
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleProfileChange = (id: string | null) => {
    setSelectedProfileId(id);
    preferences.set('lastSelectedModelProfileId', id);
  };

  const isPreparing = dataSources.isLoading || profiles.isLoading;

  if (dataSources.isError || profiles.isError) {
    return (
      <PageState
        title="Unable to prepare Ask"
        description="Data sources or model profiles could not be loaded."
      />
    );
  }

  const activeSources = (dataSources.data ?? []).filter((source) => source.status === 'active');
  const rememberedSourceIds = sourceSelections[sourceScope] ?? [];
  const soleSource = activeSources.length === 1 ? activeSources[0] : undefined;
  const selectedSourceIds = soleSource
    ? [soleSource.id]
    : rememberedSourceIds.filter((id) => activeSources.some((source) => source.id === id)).slice(0, 10);
  const handleSourceChange = (ids: string[]) => {
    const next = { ...sourceSelections, [sourceScope]: ids };
    setSourceSelections(next);
    preferences.set('askDataSourceIdsByScope', next);
  };
  const handleTableScopeChange = (scope: SourceTableScope[]) => {
    const updatedSourceIds = new Set(scope.map((item) => item.data_source_id));
    const next = {
      ...tableSelections,
      [sourceScope]: [
        ...(tableSelections[sourceScope] ?? []).filter((item) => !updatedSourceIds.has(item.data_source_id)),
        ...scope,
      ],
    };
    setTableSelections(next);
    preferences.set('askTableSelectionsByScope', next);
  };
  const enabledProfiles = (profiles.data ?? []).filter((profile) => profile.enabled);
  const effectiveProfileId = enabledProfiles.some((profile) => profile.id === selectedProfileId)
    ? selectedProfileId
    : null;

  const handleSubmit = async () => {
    if (!question.trim() || isSubmitting || selectedSourceIds.length === 0) return;
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      handleSourceChange(selectedSourceIds);
      const conversation = await api.createConversation({
        data_source_ids: selectedSourceIds,
        table_scope: normalizeTableScope(selectedSourceIds, tableSelections[sourceScope] ?? []),
        model_profile_id: effectiveProfileId,
        title: deriveConversationTitle(question),
      });

      const state: PendingConversationState = {
        pendingQuestion: question,
        modelProfileId: effectiveProfileId,
        reasoningEffort,
      };

      navigate(`/conversations/${conversation.id}`, { state });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Unable to start conversation.');
      setIsSubmitting(false);
    }
  };

  const displayName = user?.display_name?.trim() || user?.email.split('@')[0] || 'there';
  const firstName = displayName.split(/\s+/)[0] || 'there';

  return (
    <div className="chat-workspace chat-workspace--empty">
      <main className="chat-empty-state ask-start">
        <div className="chat-empty-state__welcome">
          <div className="ask-start-greeting">
            <div className="chat-empty-state__logo-badge" aria-hidden="true">
              <BrandLogo decorative className="chat-empty-state__logo" />
            </div>
            <p className="chat-empty-state__greeting">Hi {firstName}</p>
          </div>
          <h1>What would you like to know about your data?</h1>
          <p className="ask-start-description">Explore a trend, compare results, or ask a question in your own words.</p>
        </div>
        <div className="w-full">
          {submitError && (
            <div className="p-3 mb-4 bg-[var(--db-danger-soft)] border border-[var(--db-border-default)] rounded text-xs text-[var(--db-danger)]" role="alert">
              {submitError}
            </div>
          )}
          {!isPreparing && activeSources.length === 0 && (
            <div className="p-4 mb-6 bg-[var(--db-warning-soft)] border border-[var(--db-border-default)] rounded text-xs text-[var(--db-warning)]">
              No active data sources found. Connect or activate a data source to begin.
            </div>
          )}
        </div>
        <ChatComposer
          key={sourceScope}
          question={question}
          onQuestionChange={setQuestion}
          onSubmit={handleSubmit}
          dataSources={activeSources}
          selectedDataSourceIds={selectedSourceIds}
          onDataSourceIdsChange={handleSourceChange}
          tableScope={normalizeTableScope(selectedSourceIds, tableSelections[sourceScope] ?? [])}
          onTableScopeChange={handleTableScopeChange}
          profiles={enabledProfiles}
          selectedProfileId={effectiveProfileId}
          onProfileIdChange={handleProfileChange}
          reasoningEffort={reasoningEffort}
          onReasoningEffortChange={setReasoningEffort}
          isSubmitting={isSubmitting}
          disabled={!isPreparing && activeSources.length === 0}
          placement="inline"
        />
        <div className="ask-start-footer">
          {activeSources.some((source) => source.kind === 'powerbi' && selectedSourceIds.includes(source.id)) && <PowerBIConnectionStatus />}
          <span className="ask-start-keyboard-hint">Enter to send · Shift + Enter for a new line</span>
        </div>
      </main>
    </div>
  );
}

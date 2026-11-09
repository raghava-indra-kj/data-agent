import { useEffect, useRef, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { Button } from '@heroui/react';
import {
  ArrowUp,
  Check,
  Database,
  LayoutTemplate,
  Loader2,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import type { DataSource, ModelProfile } from '../../api/types';
import { SingleSelect } from '../../components/SingleSelect';
import type { AgentInstruction } from '../../settings/api/instructions-api';
import { useInstructions } from '../../settings/hooks/useInstructions';
import {
  REASONING_EFFORT_LABELS,
  effectiveProfile,
  supportsEffort,
  type ReasoningEffort,
} from '../reasoning-effort';
import { ComposerDataScope } from './ComposerDataScope';
import { ComposerPopover } from './ComposerPopover';
import { normalizeTableScope, tableScopeLabel, type SourceTableScope } from './table-scope';
import './ChatComposer.css';

type ChatComposerProps = {
  question: string;
  onQuestionChange(value: string): void;
  onSubmit(): Promise<void> | void;
  dataSources: DataSource[];
  selectedDataSourceIds: string[];
  onDataSourceIdsChange(ids: string[]): void;
  profiles: ModelProfile[];
  selectedProfileId: string | null;
  onProfileIdChange(id: string | null): void;
  /** The conversation's profile, or the workspace default when absent. */
  fallbackProfileId?: string | null;
  reasoningEffort: ReasoningEffort | null;
  onReasoningEffortChange(effort: ReasoningEffort | null): void;
  isSubmitting?: boolean;
  disabled?: boolean;
  placeholder?: string;
  placement?: 'docked' | 'inline';
  dataSourceSelection?: 'editable' | 'hidden';
  inputLabel?: string;
  containerRef?: Ref<HTMLDivElement>;
  status?: ReactNode;
  tableScope?: SourceTableScope[];
  onTableScopeChange?(scope: SourceTableScope[]): void;
};

type OpenPopover = 'scope' | 'templates' | 'settings' | null;

export function ChatComposer({
  question,
  onQuestionChange,
  onSubmit,
  dataSources,
  selectedDataSourceIds,
  onDataSourceIdsChange,
  profiles,
  selectedProfileId,
  onProfileIdChange,
  fallbackProfileId,
  reasoningEffort,
  onReasoningEffortChange,
  isSubmitting = false,
  disabled = false,
  placeholder = 'Ask a question about your business data…',
  placement = 'docked',
  dataSourceSelection = 'editable',
  inputLabel = 'Ask a question',
  containerRef,
  status,
  tableScope,
  onTableScopeChange,
}: ChatComposerProps) {
  const [openPopover, setOpenPopover] = useState<OpenPopover>(null);
  const [skillSearch, setSkillSearch] = useState('');
  const [autocompleteDismissed, setAutocompleteDismissed] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const instructionsQuery = useInstructions();
  const availableCommands = (instructionsQuery.data ?? []).filter(
    (item) => item.enabled && item.command,
  );
  const commandMatch = question.match(/^\/([a-zA-Z0-9_-]*)$/);
  const activeCommandMatch = question.match(/^\/([a-zA-Z0-9_-]+)(?:\s+([\s\S]*))?$/);
  const activeInstruction = availableCommands.find(
    (item) => item.command?.toLowerCase() === activeCommandMatch?.[1]?.toLowerCase(),
  );
  const visibleQuestion = activeInstruction ? (activeCommandMatch?.[2] ?? '') : question;
  const commandQuery = (
    openPopover === 'templates' ? skillSearch : (commandMatch?.[1] ?? '')
  ).toLowerCase();
  const matchingCommands = availableCommands.filter((item) =>
    `${item.command} ${item.name} ${item.description ?? ''}`.toLowerCase().includes(commandQuery),
  );
  const showSuggestions = Boolean(
    commandMatch && !activeInstruction && !autocompleteDismissed && !openPopover,
  );
  const model = effectiveProfile(profiles, selectedProfileId, fallbackProfileId);
  const efforts = model?.reasoning_efforts ?? [];
  const effortLabel = reasoningEffort
    ? REASONING_EFFORT_LABELS[reasoningEffort]
    : model?.default_reasoning_effort
      ? `${REASONING_EFFORT_LABELS[model.default_reasoning_effort]} (default)`
      : 'Model default';
  const hasScope = dataSourceSelection === 'hidden' || selectedDataSourceIds.length > 0;
  const sourceNames = selectedDataSourceIds.map(
    (id) => dataSources.find((source) => source.id === id)?.name ?? 'Conversation source',
  );
  const currentTableScope = normalizeTableScope(selectedDataSourceIds, tableScope ?? []);
  const scopeTooltip = sourceNames.length
    ? `${sourceNames.join(', ')} · ${tableScopeLabel(currentTableScope)}`
    : 'Choose data sources and tables';

  const changePopover = (name: OpenPopover, open: boolean) => {
    setOpenPopover((current) => (open ? name : current === name ? null : current));
    if (open) {
      setSelectedIndex(0);
      setAutocompleteDismissed(true);
      if (name === 'templates') setSkillSearch('');
    }
  };

  useEffect(() => {
    const options = suggestionsRef.current?.querySelectorAll<HTMLElement>('[role="option"]');
    options?.[selectedIndex]?.scrollIntoView?.({ block: 'nearest' });
  }, [selectedIndex]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [visibleQuestion]);

  const selectCommand = (item?: AgentInstruction) => {
    if (!item?.command) return;
    const text = activeInstruction ? visibleQuestion : commandMatch ? '' : question;
    onQuestionChange(`/${item.command} ${text}`);
    setOpenPopover(null);
    setAutocompleteDismissed(true);
    textareaRef.current?.focus();
  };

  const chooseProfile = (id: string | null) => {
    onProfileIdChange(id);
    if (!supportsEffort(effectiveProfile(profiles, id, fallbackProfileId), reasoningEffort)) {
      onReasoningEffortChange(null);
    }
  };

  const navigateTemplates = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setSelectedIndex((index) =>
        matchingCommands.length
          ? (index + (event.key === 'ArrowDown' ? 1 : -1) + matchingCommands.length) %
            matchingCommands.length
          : 0,
      );
      return true;
    }
    if (
      (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) &&
      matchingCommands.length
    ) {
      event.preventDefault();
      selectCommand(matchingCommands[selectedIndex]);
      return true;
    }
    return false;
  };

  const templateList = (
    <div
      ref={suggestionsRef}
      className="chat-composer-popover__list"
      role="listbox"
      aria-label={openPopover === 'templates' ? 'Select a template' : 'Slash command suggestions'}
    >
      {matchingCommands.length === 0 ? (
        <p className="chat-composer-popover__empty">
          {availableCommands.length
            ? 'No matching templates.'
            : 'No command templates configured. Add them in Templates.'}
        </p>
      ) : (
        matchingCommands.map((item, index) => (
          <button
            type="button"
            role="option"
            key={item.id}
            aria-selected={index === selectedIndex}
            className={`chat-composer-option ${index === selectedIndex ? 'is-selected' : ''}`}
            onMouseEnter={() => setSelectedIndex(index)}
            onClick={() => selectCommand(item)}
          >
            <span className="chat-composer-option__label">
              <span>{item.name}</span>
            </span>
            {activeInstruction?.id === item.id && (
              <Check size={15} aria-label="Selected template" />
            )}
          </button>
        ))
      )}
    </div>
  );

  return (
    <div
      ref={containerRef}
      className={`chat-composer-deck chat-composer-deck--${placement}`}
      role="region"
      aria-label="Query composer"
    >
      {status && <div className="chat-composer-status">{status}</div>}
      <div className="chat-composer-card chat-composer-card--minimal">
        {showSuggestions && (
          <div className="chat-composer-popover chat-composer-popover--commands">
            <div className="chat-composer-popover__header">
              <strong>Templates</strong>
              <button
                type="button"
                aria-label="Close command suggestions"
                className="chat-composer-popover__close"
                onClick={() => setAutocompleteDismissed(true)}
              >
                <X size={14} />
              </button>
            </div>
            {templateList}
          </div>
        )}
        <div className="chat-composer-input">
          <textarea
            ref={textareaRef}
            className="chat-composer-textarea"
            rows={1}
            placeholder={placeholder}
            value={visibleQuestion}
            disabled={disabled}
            aria-label={inputLabel}
            onChange={(event) => {
              setSelectedIndex(0);
              setAutocompleteDismissed(false);
              onQuestionChange(
                activeInstruction
                  ? `/${activeInstruction.command} ${event.target.value}`
                  : event.target.value,
              );
            }}
            onKeyDown={(event) => {
              if (showSuggestions) {
                if (event.key === 'Escape') {
                  event.preventDefault();
                  setAutocompleteDismissed(true);
                  return;
                }
                if (navigateTemplates(event)) return;
              }
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (question.trim() && !disabled && !isSubmitting && hasScope) void onSubmit();
              }
            }}
          />
        </div>
        <div className="chat-composer-toolbar composer-icon-toolbar">
          <div className="composer-toolbar-start">
            <ComposerPopover
              label="Data scope"
              wide
              badgeCount={selectedDataSourceIds.length}
              tooltip={scopeTooltip}
              icon={<Database size={19} aria-hidden="true" />}
              isOpen={openPopover === 'scope'}
              onOpenChange={(open) => changePopover('scope', open)}
              disabled={disabled || isSubmitting}
              modified={currentTableScope.some((item) => item.mode === 'selected')}
            >
              {openPopover === 'scope' && (
                <ComposerDataScope
                  key={selectedDataSourceIds.join(',')}
                  dataSources={dataSources}
                  sourceIds={selectedDataSourceIds}
                  editable={dataSourceSelection === 'editable'}
                  tableScope={onTableScopeChange ? tableScope : undefined}
                  onClose={() => setOpenPopover(null)}
                  onApply={(ids, scope) => {
                    if (dataSourceSelection === 'editable') onDataSourceIdsChange(ids);
                    onTableScopeChange?.(scope);
                  }}
                />
              )}
            </ComposerPopover>
            <ComposerPopover
              label="Templates"
              tooltip={
                activeInstruction ? `Template: ${activeInstruction.name}` : 'Choose a template'
              }
              icon={<LayoutTemplate size={19} aria-hidden="true" />}
              isOpen={openPopover === 'templates'}
              onOpenChange={(open) => changePopover('templates', open)}
              disabled={disabled}
              modified={Boolean(activeInstruction)}
            >
              <div className="composer-popover-body">
                <label className="db-icon-search composer-source-search">
                  <Search size={15} aria-hidden="true" />
                  <input
                    autoFocus
                    type="search"
                    aria-label="Search templates"
                    className="db-icon-search__input"
                    placeholder="Search templates…"
                    value={skillSearch}
                    onChange={(event) => {
                      setSkillSearch(event.target.value);
                      setSelectedIndex(0);
                    }}
                    onKeyDown={(event) => {
                      if (event.key !== 'Tab') navigateTemplates(event);
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="chat-composer-option"
                  aria-label="Remove selected template"
                  onClick={() => {
                    if (activeInstruction) onQuestionChange(visibleQuestion);
                    setOpenPopover(null);
                    textareaRef.current?.focus();
                  }}
                >
                  No template{!activeInstruction && <Check size={15} aria-hidden="true" />}
                </button>
                {templateList}
              </div>
            </ComposerPopover>
          </div>
          <div className="composer-toolbar-end">
            <ComposerPopover
              label="Model settings"
              tooltip={`${model?.display_name ?? 'Workspace default'} · ${effortLabel}`}
              icon={<SlidersHorizontal size={19} aria-hidden="true" />}
              placement="top end"
              isOpen={openPopover === 'settings'}
              onOpenChange={(open) => changePopover('settings', open)}
              disabled={disabled}
              modified={selectedProfileId !== null || reasoningEffort !== null}
            >
              <div className="composer-popover-body composer-model-settings">
                <SingleSelect
                  label="Model"
                  value={selectedProfileId ?? 'default'}
                  onChange={(id) => chooseProfile(id === 'default' ? null : id)}
                  options={[
                    {
                      value: 'default',
                      label: `Default${effectiveProfile(profiles, null, fallbackProfileId) ? ` (${effectiveProfile(profiles, null, fallbackProfileId)?.display_name})` : ''}`,
                    },
                    ...profiles
                      .filter((profile) => profile.enabled)
                      .map((profile) => ({ value: profile.id, label: profile.display_name })),
                  ]}
                />
                {efforts.length > 0 && (
                  <SingleSelect
                    label="Reasoning effort"
                    value={reasoningEffort ?? 'default'}
                    onChange={(effort) =>
                      onReasoningEffortChange(
                        effort === 'default' ? null : (effort as ReasoningEffort),
                      )
                    }
                    options={[
                      {
                        value: 'default',
                        label: `Model default${model?.default_reasoning_effort ? ` (${REASONING_EFFORT_LABELS[model.default_reasoning_effort]})` : ''}`,
                      },
                      ...efforts.map((effort) => ({
                        value: effort,
                        label: REASONING_EFFORT_LABELS[effort],
                      })),
                    ]}
                  />
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  className="composer-reset"
                  onPress={() => {
                    onProfileIdChange(null);
                    onReasoningEffortChange(null);
                  }}
                >
                  Reset to defaults
                </Button>
              </div>
            </ComposerPopover>
            <button
              type="button"
              className="chat-send-btn"
              aria-label="Send question"
              disabled={!question.trim() || isSubmitting || disabled || !hasScope}
              onClick={() => void onSubmit()}
            >
              {isSubmitting ? (
                <Loader2 size={18} className="animate-spin" aria-hidden="true" />
              ) : (
                <ArrowUp size={20} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

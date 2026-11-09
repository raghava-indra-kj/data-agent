import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { DataSource, ModelProfile } from '../../api/types';
import type { ReasoningEffort } from '../reasoning-effort';
import { ChatComposer } from './ChatComposer';

const templates = vi.hoisted(() => [
  {
    id: 's1',
    name: 'Weekly summary',
    command: 'weekly',
    description: 'Summarize weekly movement',
    enabled: true,
  },
  {
    id: 's2',
    name: 'Trend report',
    command: 'trend',
    description: 'Explore changes over time',
    enabled: true,
  },
  { id: 's3', name: 'Disabled template', command: 'disabled', description: '', enabled: false },
]);
vi.mock('../../settings/hooks/useInstructions', () => ({
  useInstructions: () => ({ data: templates }),
}));

const source: DataSource = {
  id: 'ds1',
  organization_id: 'org1',
  name: 'Warehouse',
  kind: 'postgres',
  display_type: 'postgres',
  status: 'active',
  config: {},
  created_by: 'u1',
  last_tested_at: null,
  last_error_code: null,
  created_at: '2026-08-24T12:00:00Z',
  updated_at: '2026-08-24T12:00:00Z',
  active_file: null,
};

function EditableComposer({ onSubmit }: { onSubmit(): void }) {
  const [question, setQuestion] = useState('Show revenue');
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  return (
    <ChatComposer
      question={question}
      onQuestionChange={setQuestion}
      onSubmit={onSubmit}
      dataSources={[source]}
      selectedDataSourceIds={sourceIds}
      onDataSourceIdsChange={setSourceIds}
      profiles={[]}
      selectedProfileId={null}
      onProfileIdChange={() => undefined}
      reasoningEffort={null}
      onReasoningEffortChange={() => undefined}
      placement="inline"
    />
  );
}

describe('ChatComposer data-source scope', () => {
  it('keeps a quiet four-icon toolbar and applies the selected source count as a badge', async () => {
    const user = userEvent.setup();
    const secondSource = { ...source, id: 'ds2', name: 'Finance report', kind: 'powerbi' as const };
    function MultipleSources() {
      const [ids, setIds] = useState(['ds1']);
      return (
        <ChatComposer
          question="Compare results"
          onQuestionChange={() => undefined}
          onSubmit={() => undefined}
          dataSources={[source, secondSource]}
          selectedDataSourceIds={ids}
          onDataSourceIdsChange={setIds}
          profiles={[]}
          selectedProfileId={null}
          onProfileIdChange={() => undefined}
          reasoningEffort={null}
          onReasoningEffortChange={() => undefined}
        />
      );
    }
    render(<MultipleSources />);
    expect(
      within(screen.getByRole('region', { name: 'Query composer' })).getAllByRole('button'),
    ).toHaveLength(4);
    const trigger = screen.getByRole('button', { name: 'Data scope' });
    expect(trigger).toHaveAccessibleDescription(/1 data source selected/);
    expect(trigger.querySelector('.composer-icon-count')).toHaveTextContent('1');
    expect(screen.queryByText('Warehouse')).not.toBeInTheDocument();
    await user.click(trigger);
    await user.click(screen.getByRole('checkbox', { name: 'Include Finance report' }));
    expect(screen.getByText(/Your authorized semantic model/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'View tables for Warehouse' }));
    expect(screen.getByRole('checkbox', { name: 'Include Finance report' })).toBeChecked();
    expect(trigger.querySelector('.composer-icon-count')).toHaveTextContent('1');
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(trigger.querySelector('.composer-icon-count')).toHaveTextContent('2');
    await user.click(trigger);
    await user.click(screen.getByRole('checkbox', { name: 'Include Warehouse' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(trigger);
    expect(screen.getByRole('checkbox', { name: 'Include Warehouse' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Include Finance report' })).toBeChecked();
  });

  it('prevents selecting more than ten sources and re-enables a source when another is removed', async () => {
    const user = userEvent.setup();
    const sources = Array.from({ length: 11 }, (_, index) => ({
      ...source,
      id: `s${index}`,
      name: `Source ${index}`,
    }));
    render(
      <ChatComposer
        question="Q"
        onQuestionChange={() => undefined}
        onSubmit={() => undefined}
        dataSources={sources}
        selectedDataSourceIds={sources.slice(0, 10).map((item) => item.id)}
        onDataSourceIdsChange={() => undefined}
        profiles={[]}
        selectedProfileId={null}
        onProfileIdChange={() => undefined}
        reasoningEffort={null}
        onReasoningEffortChange={() => undefined}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    expect(screen.getByRole('checkbox', { name: 'Include Source 10' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: 'Include Source 0' }));
    expect(screen.getByRole('checkbox', { name: 'Include Source 10' })).toBeEnabled();
  });
  it('allows drafting while busy but blocks button and Enter submission', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    function DraftComposer({ busy }: { busy: boolean }) {
      const [question, setQuestion] = useState('');
      return (
        <ChatComposer
          question={question}
          onQuestionChange={setQuestion}
          onSubmit={onSubmit}
          dataSources={[]}
          selectedDataSourceIds={['ds1']}
          onDataSourceIdsChange={() => undefined}
          profiles={[]}
          selectedProfileId={null}
          onProfileIdChange={() => undefined}
          reasoningEffort={null}
          onReasoningEffortChange={() => undefined}
          dataSourceSelection="hidden"
          isSubmitting={busy}
        />
      );
    }
    const view = render(<DraftComposer busy />);
    const input = screen.getByRole('textbox', { name: 'Ask a question' });
    expect(input).toBeEnabled();
    await user.type(input, 'Compare regions');
    await user.keyboard('{Enter}');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveValue('Compare regions');
    expect(screen.getByRole('button', { name: 'Templates' })).toBeEnabled();
    view.rerender(<DraftComposer busy={false} />);
    expect(input).toHaveValue('Compare regions');
    expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled();
    await user.click(input);
    await user.keyboard('{Enter}');
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('requires an explicit source selection before the first question can be sent', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<EditableComposer onSubmit={onSubmit} />);

    const send = screen.getByRole('button', { name: 'Send question' });
    expect(send).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    await user.click(screen.getByRole('button', { name: /warehouse/i }));
    expect(send).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(send).toBeEnabled();
    await user.click(send);
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('shows locked source context for follow-ups without allowing source edits', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <ChatComposer
        question="Compare regions"
        onQuestionChange={() => undefined}
        onSubmit={onSubmit}
        dataSources={[]}
        selectedDataSourceIds={['ds1']}
        onDataSourceIdsChange={() => undefined}
        profiles={[]}
        selectedProfileId={null}
        onProfileIdChange={() => undefined}
        reasoningEffort={null}
        onReasoningEffortChange={() => undefined}
        dataSourceSelection="hidden"
        inputLabel="Ask a follow-up"
      />,
    );

    expect(screen.queryByRole('button', { name: /source/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    expect(screen.getByRole('complementary', { name: 'Conversation sources' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /Include/ })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.getByRole('textbox', { name: 'Ask a follow-up' })).toBeInTheDocument();
    expect(screen.queryByText(/read-only analytical/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('closes an open picker when clicking outside', async () => {
    const user = userEvent.setup();
    render(<EditableComposer onSubmit={() => undefined} />);

    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    expect(screen.getByRole('dialog', { name: 'Data scope' })).toBeInTheDocument();

    await user.click(screen.getByRole('textbox', { name: 'Ask a question' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Data scope' })).not.toBeInTheDocument(),
    );
  });

  it('closes an open picker with Escape and only shows one picker at a time', async () => {
    const user = userEvent.setup();
    render(<EditableComposer onSubmit={() => undefined} />);

    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    await user.click(screen.getByRole('button', { name: 'Model settings' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Data scope' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('dialog', { name: 'Model settings' })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Model settings' })).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Model settings' })).toHaveFocus(),
    );
  });
});

function SkillComposer({
  onSend,
  followUp = false,
}: {
  onSend: (text: string) => void;
  followUp?: boolean;
}) {
  const [question, setQuestion] = useState('Show revenue');
  return (
    <ChatComposer
      question={question}
      onQuestionChange={setQuestion}
      onSubmit={() => onSend(question)}
      dataSources={[source]}
      selectedDataSourceIds={['ds1']}
      onDataSourceIdsChange={() => undefined}
      profiles={[]}
      selectedProfileId={null}
      onProfileIdChange={() => undefined}
      reasoningEffort={null}
      onReasoningEffortChange={() => undefined}
      dataSourceSelection={followUp ? 'hidden' : 'editable'}
    />
  );
}
describe('composer template selection', () => {
  it('searches templates, preserves the question, and submits the selected command', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(<SkillComposer onSend={send} />);
    await user.click(screen.getByRole('button', { name: 'Templates' }));
    expect(screen.queryByRole('option', { name: /Disabled template/ })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Search templates'), 'weekly');
    expect(screen.queryByRole('option', { name: /Trend report/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('option', { name: /Weekly summary/ }));
    expect(screen.getByLabelText('Ask a question')).toHaveValue('Show revenue');
    expect(screen.queryByText('Weekly summary')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Templates' }).querySelector('.composer-icon-dot'),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText('Ask a question'), ' this week');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(send).toHaveBeenCalledWith('/weekly Show revenue this week');
  });
  it('replaces and removes a template without discarding multiline follow-up text', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(<SkillComposer onSend={send} followUp />);
    await user.click(screen.getByRole('button', { name: 'Templates' }));
    await user.click(screen.getByRole('option', { name: /Weekly summary/ }));
    await user.type(
      screen.getByLabelText('Ask a question'),
      '{Shift>}{Enter}{/Shift}Compare regions',
    );
    await user.click(screen.getByRole('button', { name: 'Templates' }));
    await user.click(screen.getByRole('option', { name: /Trend report/ }));
    expect(screen.getByLabelText('Ask a question')).toHaveValue('Show revenue\nCompare regions');
    await user.click(screen.getByRole('button', { name: 'Templates' }));
    await user.click(screen.getByLabelText('Remove selected template'));
    expect(screen.getByLabelText('Ask a question')).toHaveValue('Show revenue\nCompare regions');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(send).toHaveBeenCalledWith('Show revenue\nCompare regions');
  });
  it('supports slash suggestions and keyboard selection', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(<SkillComposer onSend={send} />);
    const input = screen.getByLabelText('Ask a question');
    await user.clear(input);
    await user.type(input, '/tre');
    expect(screen.getByRole('listbox', { name: 'Slash command suggestions' })).toBeInTheDocument();
    await user.keyboard('{Tab}');
    expect(input).toHaveValue('');
    expect(
      screen.getByRole('button', { name: 'Templates' }).querySelector('.composer-icon-dot'),
    ).toBeInTheDocument();
    await user.type(input, 'Last month');
    await user.keyboard('{Enter}');
    expect(send).toHaveBeenCalledWith('/trend Last month');
  });
});

function profile(
  id: string,
  modelName: string,
  efforts: ReasoningEffort[],
  defaultEffort: ReasoningEffort | null,
  isDefault = false,
): ModelProfile {
  return {
    id,
    organization_id: 'org1',
    connection_id: 'c1',
    display_name: id,
    model_name: modelName,
    settings: {},
    is_default: isDefault,
    enabled: true,
    created_at: '2026-10-25T00:00:00Z',
    updated_at: '2026-10-25T00:00:00Z',
    reasoning_efforts: efforts,
    default_reasoning_effort: defaultEffort,
  };
}

const reasoningProfile = profile(
  'GPT 5.5',
  'gpt-5.5',
  ['none', 'low', 'medium', 'high', 'xhigh'],
  'medium',
  true,
);
const lowOnlyProfile = profile('O3', 'o3', ['low', 'medium', 'high'], 'medium');
const plainProfile = profile('GPT 4o', 'gpt-4o', [], null);

function EffortComposer({
  profiles,
  onSend,
}: {
  profiles: ModelProfile[];
  onSend(effort: ReasoningEffort | null): void;
}) {
  const [profileId, setProfileId] = useState<string | null>(null);
  const [effort, setEffort] = useState<ReasoningEffort | null>(null);
  return (
    <ChatComposer
      question="Show revenue"
      onQuestionChange={() => undefined}
      onSubmit={() => onSend(effort)}
      dataSources={[]}
      selectedDataSourceIds={['ds1']}
      onDataSourceIdsChange={() => undefined}
      profiles={profiles}
      selectedProfileId={profileId}
      onProfileIdChange={setProfileId}
      reasoningEffort={effort}
      onReasoningEffortChange={setEffort}
      dataSourceSelection="hidden"
    />
  );
}

describe('composer reasoning effort', () => {
  it('offers only the efforts the default model supports and sends the chosen one', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(<EffortComposer profiles={[reasoningProfile, plainProfile]} onSend={send} />);

    await user.click(screen.getByRole('button', { name: 'Model settings' }));
    await user.click(screen.getByRole('button', { name: /Reasoning effort/ }));
    const options = within(screen.getByRole('listbox'))
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(options).toEqual([
      'Model default (Medium)',
      'None',
      'Low',
      'Medium',
      'High',
      'Extra high',
    ]);
    await user.click(screen.getByRole('option', { name: 'High' }));
    expect(screen.getByRole('button', { name: /Reasoning effort/ })).toHaveTextContent('High');
    await user.keyboard('{Escape}');

    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(send).toHaveBeenLastCalledWith('high');
  });

  it('hides the control for models without reasoning and resets an effort the new model rejects', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(
      <EffortComposer profiles={[reasoningProfile, lowOnlyProfile, plainProfile]} onSend={send} />,
    );

    await user.click(screen.getByRole('button', { name: 'Model settings' }));
    await user.click(screen.getByRole('button', { name: /Reasoning effort/ }));
    await user.click(screen.getByRole('option', { name: 'High' }));
    // o3 also accepts high, so the choice stays.
    await user.click(screen.getByRole('button', { name: / Model$/ }));
    await user.click(screen.getByRole('option', { name: /O3/ }));
    expect(screen.getByRole('button', { name: /Reasoning effort/ })).toHaveTextContent('High');

    await user.click(screen.getByRole('button', { name: /Reasoning effort/ }));
    await user.click(screen.getByRole('option', { name: 'Low' }));
    await user.click(screen.getByRole('button', { name: / Model$/ }));
    await user.click(screen.getByRole('option', { name: /GPT 4o/ }));
    expect(screen.queryByRole('button', { name: /Reasoning effort/ })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(send).toHaveBeenLastCalledWith(null);
  });
});

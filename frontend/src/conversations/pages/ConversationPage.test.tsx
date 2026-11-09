import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../../test/server';
import { queryKeys } from '../../api/queryKeys';
import type { ManagedJob } from '../../jobs/types';
import { getLocalTimeZone } from '../../lib/datetime';

const manager = vi.hoisted(() => ({
  jobs: [] as ManagedJob[],
  registerJob: vi.fn(async () => undefined),
  cancel: vi.fn(async () => undefined),
}));
const answerRenders = vi.hoisted(() => vi.fn());
vi.mock('../components/AssistantMarkdown', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../components/AssistantMarkdown')>();
  const { Profiler } = await import('react');
  return {
    AssistantMarkdown: (props: { content: string }) => (
      <Profiler id="answer-markdown" onRender={answerRenders}>
        <actual.AssistantMarkdown {...props} />
      </Profiler>
    ),
  };
});
// Resolve fetch after MSW starts instead of capturing the original fetch during imports.
vi.mock('openapi-fetch', async (importOriginal) => {
  const actual = await importOriginal<typeof import('openapi-fetch')>();
  return {
    ...actual,
    default: (options: Parameters<typeof actual.default>[0]) =>
      actual.default({
        ...options,
        fetch: (...args: Parameters<typeof fetch>) => globalThis.fetch(...args),
      }),
  };
});
vi.mock('../../organizations/OrganizationProvider', () => ({
  useOrganization: () => ({ activeOrganization: { id: 'org-1', name: 'Org', role: 'owner' } }),
}));
vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { display_name: 'Alex Morgan', email: 'alex@example.com' } }),
}));
vi.mock('../../jobs/JobManagerProvider', () => ({
  useJobManager: () => ({
    ...manager,
    activeJobs: manager.jobs.filter(
      (entry) => entry.job.status === 'running' || entry.job.status === 'queued',
    ),
    latestEvent: () => undefined,
    currentLabel: () => null,
    isLoading: false,
  }),
}));

import { ConversationPage } from './ConversationPage';
import { RecentConversations } from '../components/RecentConversations';
import { useConversationList } from '../hooks/useConversations';

const conversation = {
  id: 'c1',
  organization_id: 'org-1',
  title: 'Revenue analysis',
  created_by: 'u1',
  model_profile_id: null,
  data_source_ids: ['ds1'],
  created_at: '2026-08-24T12:00:00Z',
  updated_at: '2026-08-24T12:00:00Z',
};
const source = {
  id: 'ds1',
  organization_id: 'org-1',
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

function RecentChats() {
  const chats = useConversationList();
  return <RecentConversations conversations={chats.conversations} />;
}

const page = <T,>(items: T[], next_cursor: string | null = null) => ({
  items,
  next_cursor,
  has_more: next_cursor !== null,
});
const messagePages = (...pages: unknown[][]) => ({
  pages: pages.map((items) => page(items)),
  pageParams: pages.map(() => null),
});

function renderPage(state?: object, withRecent = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname: '/conversations/c1', state }]}>
        {withRecent ? <RecentChats /> : null}
        <Routes>
          <Route path="/conversations/:conversationId" element={<ConversationPage />} />
          <Route path="/ask" element={<div>Ask page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

function baseHandlers(messageProvider: () => unknown[] = () => []) {
  server.use(
    http.get('http://localhost:12201/api/v1/conversations/c1', () =>
      HttpResponse.json(conversation),
    ),
    http.get('http://localhost:12201/api/v1/conversations/c1/messages', () =>
      HttpResponse.json(page(messageProvider())),
    ),
    http.get('http://localhost:12201/api/v1/conversations', () =>
      HttpResponse.json(page([conversation])),
    ),
    http.get('http://localhost:12201/api/v1/data-sources', () => HttpResponse.json([source])),
    http.get('http://localhost:12201/api/v1/models/profiles', () => HttpResponse.json([])),
    http.get('http://localhost:12201/api/v1/instructions', () => HttpResponse.json([])),
    http.get('http://localhost:12201/api/v1/jobs/:jobId/execution', () =>
      HttpResponse.json({ tools: [], sql: [], models: [], artifacts: [] }),
    ),
  );
}

describe('durable conversation workspace', () => {
  beforeEach(() => {
    manager.jobs = [];
    manager.registerJob.mockClear();
    manager.cancel.mockClear();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('loads the newest messages first and earlier pages on demand', async () => {
    const message = (id: string, role: string, minute: number) => ({
      id,
      conversation_id: 'c1',
      role,
      content: `Message ${id}`,
      job_id: null,
      metadata: {},
      created_at: `2026-08-24T12:0${minute}:00Z`,
    });
    const cursors: (string | null)[] = [];
    baseHandlers();
    server.use(
      http.get('http://localhost:12201/api/v1/conversations/c1/messages', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        cursors.push(cursor);
        return HttpResponse.json(
          cursor === 'older'
            ? page([message('m1', 'user', 1), message('m2', 'assistant', 2)])
            : page([message('m3', 'user', 3), message('m4', 'assistant', 4)], 'older'),
        );
      }),
    );
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText('Message m4')).toBeInTheDocument();
    expect(screen.queryByText('Message m1')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load more' }));

    expect(await screen.findByText('Message m1')).toBeInTheDocument();
    expect(cursors).toEqual([null, 'older']);
    const stream = screen.getByLabelText('Conversation messages');
    const order = ['m1', 'm2', 'm3', 'm4'].map((id) => stream.textContent!.indexOf(`Message ${id}`));
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(screen.getByText('Start of conversation')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('replaces a read-only streamed preview with the authoritative saved answer', async () => {
    const question = {
      id: 'q1',
      conversation_id: 'c1',
      role: 'user' as const,
      content: 'Summarize orders',
      job_id: 'j1',
      metadata: {},
      created_at: conversation.created_at,
    };
    baseHandlers(() => [question]);
    manager.jobs = [
      {
        job: {
          id: 'j1',
          organization_id: 'org-1',
          conversation_id: 'c1',
          job_type: 'chat_query',
          status: 'running',
          input: {},
          result: null,
          requested_by: 'u1',
          attempt_count: 1,
          max_attempts: 3,
          cancel_requested_at: null,
          error_code: null,
          error_message: null,
          created_at: conversation.created_at,
          started_at: conversation.created_at,
          finished_at: null,
        },
        answer: { streamId: 's1', text: 'An early finding.' },
        events: [],
        lastSeenSequence: 2,
        connectionState: 'connected',
      },
    ];
    const client = renderPage();
    expect(await screen.findByRole('article', { name: 'Answer being written' })).toHaveTextContent(
      'An early finding.',
    );
    expect(screen.queryByRole('button', { name: 'Present answer' })).not.toBeInTheDocument();
    await act(async () => {
      manager.jobs = [
        { ...manager.jobs[0]!, job: { ...manager.jobs[0]!.job, status: 'succeeded' } },
      ];
      client.setQueryData(
        queryKeys.conversations.messages('org-1', 'c1'),
        messagePages([
          question,
          {
            ...question,
            id: 'a1',
            role: 'assistant',
            content: 'The final saved answer.',
            metadata: {},
          },
        ]),
      );
    });
    expect(await screen.findByText('The final saved answer.')).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'Answer being written' })).not.toBeInTheDocument();
    expect(screen.queryByText('An early finding.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Present answer' })).toBeEnabled();
  });

  it('updates a follow-up draft without rerendering the report, and still renders new answer data', async () => {
    const answer = {
      id: 'm-answer',
      conversation_id: 'c1',
      role: 'assistant',
      content: '# Customer report\n\nCurrent backlog.',
      job_id: null,
      metadata: {},
      created_at: '2026-08-24T12:00:00Z',
    };
    baseHandlers(() => [answer]);
    const client = renderPage();
    const user = userEvent.setup();
    await screen.findByText('Current backlog.');
    const input = screen.getByRole('textbox', { name: 'Ask a follow-up' });
    answerRenders.mockClear();

    await user.type(input, 'Compare the customers{Shift>}{Enter}{/Shift}for this week');
    expect(input).toHaveValue('Compare the customers\nfor this week');
    expect(answerRenders).not.toHaveBeenCalled();

    await act(async () => {
      client.setQueryData(
        queryKeys.conversations.messages('org-1', 'c1'),
        messagePages([{ ...answer, content: '# Customer report\n\nUpdated backlog.' }]),
      );
    });
    expect(await screen.findByText('Updated backlog.')).toBeInTheDocument();
    expect(answerRenders).toHaveBeenCalled();
    expect(input).toHaveValue('Compare the customers\nfor this week');
  });

  it('preserves a new draft typed while the previous submission is pending', async () => {
    baseHandlers();
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    const received = vi.fn();
    server.use(
      http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
        received(await request.json());
        await pending;
        return HttpResponse.json({ message_id: 'm-new', job_id: 'j-new' }, { status: 202 });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByRole('textbox', { name: 'Ask a follow-up' });
    await user.type(input, 'Original question{Enter}');
    await waitFor(() => expect(received).toHaveBeenCalledOnce());
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled();
    await user.clear(input);
    await user.type(input, 'Next question draft{Enter}');
    expect(received).toHaveBeenCalledOnce();
    release();
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j-new'));
    expect(input).toHaveValue('Next question draft');
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled(),
    );
  });

  it('submits the latest answer suggestion in the same conversation without clearing a composer draft', async () => {
    baseHandlers(() => [
      {
        id: 'old',
        conversation_id: 'c1',
        role: 'assistant',
        content: 'Old answer',
        job_id: null,
        metadata: { follow_up_suggestions: ['Old suggestion?'] },
        created_at: '2026-08-24T12:00:00Z',
      },
      {
        id: 'latest',
        conversation_id: 'c1',
        role: 'assistant',
        content: 'Latest answer',
        job_id: 'answer-job',
        metadata: { follow_up_suggestions: ['Compare customers?'] },
        created_at: '2026-08-24T12:01:00Z',
      },
    ]);
    const received = vi.fn();
    server.use(
      http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
        received(await request.json());
        return HttpResponse.json(
          { message_id: 'm-suggestion', job_id: 'j-suggestion' },
          { status: 202 },
        );
      }),
    );
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByRole('textbox', { name: 'Ask a follow-up' });
    await user.type(input, 'My draft');
    expect(screen.queryByRole('button', { name: 'Old suggestion?' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Compare customers?' }));
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j-suggestion'));
    expect(received).toHaveBeenCalledWith({
      content: 'Compare customers?',
      model_profile_id: null,
      reasoning_effort: null,
      timezone: getLocalTimeZone(),
    });
    expect(input).toHaveValue('My draft');
  });

  it('answers clarifying questions in one step and keeps the chat box closed until then', async () => {
    const question = {
      id: 'q1',
      conversation_id: 'c1',
      role: 'user',
      content: 'Show overdue backlog',
      job_id: 'j1',
      metadata: {},
      created_at: '2026-08-24T12:00:00Z',
    };
    const asked = {
      id: 'a1',
      conversation_id: 'c1',
      role: 'assistant',
      content: '# A few questions before I continue',
      job_id: 'j1',
      metadata: {
        clarification: {
          schema_version: 1,
          reason: 'The division changes the totals.',
          questions: [
            {
              id: 'division',
              kind: 'choice',
              prompt: 'Which division?',
              options: [{ label: 'BID' }, { label: 'LSG' }, { label: 'Other', is_other: true }],
            },
            { id: 'period', kind: 'text', prompt: 'Which period?' },
          ],
        },
      },
      created_at: '2026-08-24T12:00:05Z',
    };
    let posted: unknown;
    baseHandlers(() => [question, asked]);
    server.use(
      http.post(
        'http://localhost:12201/api/v1/conversations/c1/messages/a1/clarification-answers',
        async ({ request }) => {
          posted = await request.json();
          return HttpResponse.json({ message_id: 'm2', job_id: 'j2' }, { status: 202 });
        },
      ),
    );
    renderPage();
    const user = userEvent.setup();

    const composer = await screen.findByRole('textbox', { name: 'Ask a follow-up' });
    expect(composer).toBeDisabled();
    expect(composer).toHaveAttribute('placeholder', 'Answer the questions above to continue');

    await user.click(await screen.findByRole('radio', { name: 'BID' }));
    await user.type(screen.getByRole('textbox', { name: 'Which period?' }), 'September');
    await user.click(screen.getByRole('button', { name: 'Send answers' }));

    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j2'));
    expect(posted).toEqual({
      answers: [
        { question_id: 'division', selected: ['BID'] },
        { question_id: 'period', text: 'September' },
      ],
    });
  });

  it('answers a paused analysis on the same job, can cancel it, and closes once it ends', async () => {
    const created = '2026-08-24T12:00:00Z';
    const question = {
      id: 'q1',
      conversation_id: 'c1',
      role: 'user',
      content: 'Show overdue backlog',
      job_id: 'j1',
      metadata: {},
      created_at: created,
    };
    const asked = {
      id: 'a1',
      conversation_id: 'c1',
      role: 'assistant',
      content: '# A few questions before I continue',
      job_id: 'j1',
      metadata: {
        resumable: true,
        clarification: {
          reason: 'The division changes the totals.',
          questions: [
            {
              id: 'division',
              kind: 'choice',
              prompt: 'Which division?',
              options: [{ label: 'BID' }, { label: 'Other', is_other: true }],
            },
          ],
        },
      },
      created_at: '2026-08-24T12:00:05Z',
    };
    const pausedJob = (status: string) => ({
      job: {
        id: 'j1',
        organization_id: 'org-1',
        conversation_id: 'c1',
        job_type: 'chat_query',
        status,
        input: {},
        result: null,
        requested_by: 'u1',
        attempt_count: 1,
        max_attempts: 3,
        cancel_requested_at: null,
        error_code: null,
        error_message: null,
        created_at: created,
        started_at: created,
        finished_at: null,
      },
      events: [],
      lastSeenSequence: 3,
      connectionState: 'closed',
    }) as ManagedJob;
    let posted: unknown;
    baseHandlers(() => [question, asked]);
    server.use(
      http.post(
        'http://localhost:12201/api/v1/conversations/c1/messages/a1/clarification-answers',
        async ({ request }) => {
          posted = await request.json();
          return HttpResponse.json({ message_id: 'm2', job_id: 'j1' }, { status: 202 });
        },
      ),
    );
    manager.jobs = [pausedJob('waiting_for_input')];
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Cancel analysis' }));
    expect(manager.cancel).toHaveBeenCalledWith('j1');

    await user.click(screen.getByRole('radio', { name: 'BID' }));
    await user.click(screen.getByRole('button', { name: 'Send answers' }));
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j1'));
    expect(posted).toEqual({ answers: [{ question_id: 'division', selected: ['BID'] }] });
  });

  it('closes the questions of a paused analysis that was cancelled', async () => {
    const created = '2026-08-24T12:00:00Z';
    baseHandlers(() => [
      {
        id: 'q1',
        conversation_id: 'c1',
        role: 'user',
        content: 'Show overdue backlog',
        job_id: 'j1',
        metadata: {},
        created_at: created,
      },
      {
        id: 'a1',
        conversation_id: 'c1',
        role: 'assistant',
        content: '# A few questions before I continue',
        job_id: 'j1',
        metadata: {
          resumable: true,
          clarification: {
            reason: 'Why',
            questions: [{ id: 'period', kind: 'text', prompt: 'Which period?' }],
          },
        },
        created_at: '2026-08-24T12:00:05Z',
      },
    ]);
    manager.jobs = [
      {
        job: {
          id: 'j1',
          organization_id: 'org-1',
          conversation_id: 'c1',
          job_type: 'chat_query',
          status: 'cancelled',
          input: {},
          result: null,
          requested_by: 'u1',
          attempt_count: 1,
          max_attempts: 3,
          cancel_requested_at: created,
          error_code: null,
          error_message: null,
          created_at: created,
          started_at: created,
          finished_at: created,
        },
        events: [],
        lastSeenSequence: 3,
        connectionState: 'closed',
      } as ManagedJob,
    ];
    renderPage();
    expect(await screen.findByText('Not answered')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send answers' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask a follow-up' })).toBeEnabled();
  });

  it('renames the chat in the header and recent list without submitting an analysis', async () => {
    baseHandlers();
    let saved = { ...conversation };
    server.use(
      http.get('http://localhost:12201/api/v1/conversations/c1', () =>
        HttpResponse.json(saved),
      ),
      http.get('http://localhost:12201/api/v1/conversations', () =>
        HttpResponse.json(page([saved])),
      ),
      http.patch('http://localhost:12201/api/v1/conversations/c1', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Monthly revenue review' });
        saved = { ...saved, title: 'Monthly revenue review' };
        return HttpResponse.json(saved);
      }),
    );
    const client = renderPage(undefined, true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename chat' }));
    const input = screen.getByRole('textbox', { name: 'Chat title' });
    expect(input).toHaveValue('Revenue analysis');
    await user.clear(input);
    await user.type(input, '  Monthly revenue review  ');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(
      await screen.findByRole('heading', { name: 'Monthly revenue review' }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /Monthly revenue review/ })).toBeInTheDocument();
    await client.invalidateQueries({ queryKey: ['conversations', 'org-1'] });
    expect(screen.getByRole('heading', { name: 'Monthly revenue review' })).toBeInTheDocument();
    expect(manager.registerJob).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename chat' }));
    expect(screen.getByRole('textbox', { name: 'Chat title' })).toHaveValue(
      'Monthly revenue review',
    );
  });

  it('cancels a rename and rejects a blank title without saving', async () => {
    baseHandlers();
    const patch = vi.fn();
    server.use(http.patch('http://localhost:12201/api/v1/conversations/c1', patch));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename chat' }));
    await user.clear(screen.getByRole('textbox', { name: 'Chat title' }));
    await user.type(screen.getByRole('textbox', { name: 'Chat title' }), 'Other title');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('heading', { name: 'Revenue analysis' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename chat' }));
    const input = screen.getByRole('textbox', { name: 'Chat title' });
    expect(input).toHaveValue('Revenue analysis');
    await user.clear(input);
    await user.type(input, '   ');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a chat title.');
    expect(patch).not.toHaveBeenCalled();
  });

  it('keeps the old title and editable draft when a rename fails', async () => {
    baseHandlers();
    server.use(
      http.patch('http://localhost:12201/api/v1/conversations/c1', () =>
        HttpResponse.json(
          { error: { code: 'RENAME_FAILED', message: 'Unable to save the title.' } },
          { status: 503 },
        ),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename chat' }));
    const input = screen.getByRole('textbox', { name: 'Chat title' });
    await user.clear(input);
    await user.type(input, 'New title');
    await user.type(input, '{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to save the title.');
    expect(input).toHaveValue('New title');
    expect(
      screen.getByRole('heading', { name: 'Revenue analysis', hidden: true }),
    ).toBeInTheDocument();
  });

  it('submits the pending first question once, renders the durable user ID immediately, and registers its global job', async () => {
    baseHandlers();
    let submissions = 0;
    server.use(
      http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
        submissions += 1;
        expect(await request.json()).toEqual({
          content: 'Why did revenue fall?',
          model_profile_id: null,
          reasoning_effort: 'high',
          timezone: getLocalTimeZone(),
        });
        return HttpResponse.json({ message_id: 'm-durable', job_id: 'j-chat' }, { status: 202 });
      }),
    );
    renderPage({ pendingQuestion: 'Why did revenue fall?', modelProfileId: null, reasoningEffort: 'high' });
    expect(await screen.findByText('Why did revenue fall?')).toBeInTheDocument();
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j-chat'));
    expect(submissions).toBe(1);
    expect(document.querySelector('[data-message-id="m-durable"]')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Conversation actions' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New Analysis' })).not.toBeInTheDocument();
  });

  it('refetches and renders the persisted assistant answer after query reconciliation', async () => {
    let completed = false;
    baseHandlers(() =>
      completed
        ? [
            {
              id: 'm1',
              conversation_id: 'c1',
              role: 'user',
              content: 'Revenue?',
              job_id: 'j1',
              metadata: {},
              created_at: '2026-08-24T12:00:00Z',
            },
            {
              id: 'm2',
              conversation_id: 'c1',
              role: 'assistant',
              content: '**Revenue declined 8%.**',
              job_id: 'j1',
              metadata: {},
              created_at: '2026-08-24T12:00:03Z',
            },
          ]
        : [
            {
              id: 'm1',
              conversation_id: 'c1',
              role: 'user',
              content: 'Revenue?',
              job_id: 'j1',
              metadata: {},
              created_at: '2026-08-24T12:00:00Z',
            },
          ],
    );
    const client = renderPage();
    expect(await screen.findByText('Revenue?')).toBeInTheDocument();
    completed = true;
    await client.invalidateQueries({ queryKey: ['conversations', 'org-1', 'messages', 'c1'] });
    expect(await screen.findByText('Revenue declined 8%.')).toBeInTheDocument();
    const assistantCard = document.querySelector('[data-message-id="m2"] .assistant-card');
    expect(assistantCard?.querySelector('.assistant-card-header')).toBeNull();
    expect(assistantCard?.querySelector('.assistant-card-content')).not.toBeNull();
    expect(assistantCard?.querySelector('.assistant-card-footer')).not.toBeNull();
    expect(
      assistantCard?.querySelector('.assistant-card-footer .assistant-card-actions'),
    ).not.toBeNull();
    expect(screen.queryByRole('button', { name: /execution ledger/i })).not.toBeInTheDocument();
  });

  it('changes the tables of an existing conversation for its next questions', async () => {
    baseHandlers();
    const saved: unknown[] = [];
    server.use(
      http.get('http://localhost:12201/api/v1/data-sources/ds1/tables', () =>
        HttpResponse.json({
          knowledge_version_id: 'v1',
          items: [{ schema: 'dbo', name: 'orders', object_type: 'table', column_count: 4 }],
          next_cursor: null,
        }),
      ),
      http.put('http://localhost:12201/api/v1/conversations/c1/table-scope', async ({ request }) => {
        const body = (await request.json()) as { table_scope: unknown };
        saved.push(body);
        return HttpResponse.json({ ...conversation, table_scope: body.table_scope });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Data scope' }));
    await user.click(await screen.findByRole('radio', { name: 'Choose tables' }));
    await user.click(await screen.findByRole('checkbox', { name: /orders/ }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(await screen.findByRole('button', { name: 'Data scope' })).toBeInTheDocument();
    expect(saved).toEqual([
      {
        table_scope: [
          { data_source_id: 'ds1', mode: 'selected', tables: [{ schema: 'dbo', name: 'orders' }] },
        ],
      },
    ]);
  });

  it('keeps source context behind the conversation menu and removes scrolling controls', async () => {
    baseHandlers();
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Revenue analysis' });
    expect(screen.queryByRole('button', { name: 'Scroll to top' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Scroll to bottom' })).not.toBeInTheDocument();
    expect(screen.queryByText('Warehouse')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Conversation actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Conversation details' }));
    expect(screen.getByRole('dialog', { name: 'Conversation details' })).toHaveTextContent(
      'Warehouse',
    );
    await user.keyboard('{Escape}');
  });

  it('creates an independent durable job for a follow-up without waiting for an earlier answer', async () => {
    baseHandlers(() => [
      {
        id: 'm1',
        conversation_id: 'c1',
        role: 'user',
        content: 'Initial question',
        job_id: 'j1',
        metadata: {},
        created_at: '2026-08-24T12:00:00Z',
      },
    ]);
    server.use(
      http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
        expect(await request.json()).toEqual({
          content: 'Now compare enterprise customers.',
          model_profile_id: null,
          reasoning_effort: null,
          timezone: getLocalTimeZone(),
        });
        return HttpResponse.json({ message_id: 'm-follow', job_id: 'j-follow' }, { status: 202 });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByRole('textbox', { name: 'Ask a follow-up' });
    await user.type(input, 'Now compare enterprise customers.');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(await screen.findByText('Now compare enterprise customers.')).toBeInTheDocument();
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('j-follow'));
  });

  it('keeps a running analysis alive when live updates are reconnecting', async () => {
    baseHandlers();
    manager.jobs = [
      {
        job: {
          id: 'j1',
          organization_id: 'org-1',
          job_type: 'chat_query',
          status: 'running',
          requested_by: 'u1',
          conversation_id: 'c1',
          input: {},
          result: null,
          attempt_count: 1,
          max_attempts: 3,
          cancel_requested_at: null,
          error_code: null,
          error_message: null,
          created_at: '2026-08-24T12:00:00Z',
          started_at: '2026-08-24T12:00:01Z',
          finished_at: null,
        },
        events: [
          {
            sequence: 2,
            event_type: 'sql.started',
            level: 'info',
            payload: {},
            created_at: '2026-08-24T12:00:02Z',
          },
        ],
        lastSeenSequence: 2,
        connectionState: 'reconnecting',
      },
    ];
    renderPage();
    expect(await screen.findByText('Retrieving the data…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Stop/i })).toBeEnabled();
    expect(screen.queryByText(/analysis failed/i)).not.toBeInTheDocument();
  });

  it('shows a safe failed-job state without rendering hidden event payloads', async () => {
    baseHandlers();
    manager.jobs = [
      {
        job: {
          id: 'j1',
          organization_id: 'org-1',
          job_type: 'chat_query',
          status: 'failed',
          requested_by: 'u1',
          conversation_id: 'c1',
          input: {},
          result: null,
          attempt_count: 1,
          max_attempts: 3,
          cancel_requested_at: null,
          error_code: 'QUERY_TIMEOUT',
          error_message: 'The query exceeded the allowed duration.',
          created_at: '2026-08-24T12:00:00Z',
          started_at: '2026-08-24T12:00:01Z',
          finished_at: '2026-08-24T12:00:05Z',
        },
        events: [
          {
            sequence: 1,
            event_type: 'tool.started',
            level: 'info',
            payload: { hidden_prompt: 'SECRET_REASONING' },
            created_at: '2026-08-24T12:00:01Z',
          },
        ],
        lastSeenSequence: 1,
        connectionState: 'closed',
      },
    ];
    renderPage();
    expect(await screen.findByText('This analysis took too long')).toBeInTheDocument();
    expect(screen.queryByText('SECRET_REASONING')).not.toBeInTheDocument();
  });
});

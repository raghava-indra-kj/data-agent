import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { queryKeys } from '../../api/queryKeys';
import { PageError, PageLoading, PageState } from '../../components/PageState';
import { listDataSources } from '../../data-sources/api/data-source-api';
import { listProfiles } from '../../models/api/models-api';
import { useJobManager } from '../../jobs/JobManagerProvider';
import { isTerminalJobStatus, isWaitingJobStatus } from '../../jobs/types';
import { useOrganization } from '../../organizations/OrganizationProvider';
import { useAuth } from '../../auth/AuthProvider';
import * as api from '../api/conversation-api';
import { AnalysisFailure } from '../components/AnalysisFailure';
import { AnalysisProgress } from '../components/AnalysisProgress';
import { StreamingAnswer } from '../components/StreamingAnswer';
import { ConversationMessage } from '../components/ConversationMessage';
import { FollowUpChatComposer } from '../components/FollowUpChatComposer';
import { ConversationActions } from '../components/ConversationActions';
import { orderConversationTurns } from '../components/conversation-turns';
import {
  clarificationAnswers,
  clarificationRequest,
  resumesPausedAnalysis,
  type ClarificationAnswer,
} from '../clarification';
import { LoadMoreSentinel } from '../../components/LoadMoreSentinel';
import {
  appendMessage,
  useConversation,
  useConversationMessages,
  useUpdateTableScope,
} from '../hooks/useConversations';
import type { ReasoningEffort } from '../reasoning-effort';
import { PowerBICanvas, type ReportCanvasHandle } from '../../power-bi/PowerBICanvas';
import { ReportLauncher } from '../../power-bi/ReportLauncher';
import type { PowerBIReport } from '../../power-bi/api';

type PendingConversationState = {
  pendingQuestion?: string;
  modelProfileId?: string | null;
  reasoningEffort?: ReasoningEffort | null;
} | null;

function errorMessage(error: unknown) {
  return error && typeof error === 'object' && 'message' in error
    ? String(error.message)
    : 'Unable to submit the question.';
}

export function ConversationPage() {
  const { conversationId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activeOrganization } = useOrganization();
  const { user } = useAuth();
  const orgId = activeOrganization?.id ?? null;
  const [selectedReport, setSelectedReport] = useState<PowerBIReport | null>(null);
  const reportCanvas = useRef<ReportCanvasHandle>(null);
  useEffect(() => { setSelectedReport(null); }, [conversationId, orgId, user?.id]);

  const conversation = useConversation(conversationId);
  const messages = useConversationMessages(conversationId);
  const updateTableScope = useUpdateTableScope();
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

  const jobManager = useJobManager();
  const pendingStarted = useRef(false);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const followScrollRef = useRef(true);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [composerElement, setComposerElement] = useState<HTMLDivElement | null>(null);
  const [initialSubmitError, setInitialSubmitError] = useState<string | null>(null);

  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  // Follow-ups start with the effort the first question was asked with.
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort | null>(
    () => (location.state as PendingConversationState)?.reasoningEffort ?? null,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const sourceNames = useMemo(
    () => Object.fromEntries((dataSources.data ?? []).map((source) => [source.id, source.name])),
    [dataSources.data],
  );

  const conversationJobs = useMemo(
    () =>
      jobManager.jobs
        .filter((entry) => entry.job.conversation_id === conversationId)
        .sort((a, b) => Date.parse(a.job.created_at) - Date.parse(b.job.created_at)),
    [conversationId, jobManager.jobs],
  );

  const activeRunningJob =
    conversationJobs.find((entry) => entry.job.status === 'running') ??
    conversationJobs.find((entry) => entry.job.status === 'queued');

  const appendOptimisticMessage = useCallback(
    (accepted: api.MessageAccepted, content: string) => {
      if (!conversationId) return;
      appendMessage(queryClient, orgId, {
        id: accepted.message_id,
        conversation_id: conversationId,
        role: 'user',
        content,
        job_id: accepted.job_id,
        metadata: {},
        created_at: new Date().toISOString(),
      });
    },
    [conversationId, orgId, queryClient],
  );

  const submit = useCallback(
    async (content: string, modelProfileId?: string | null, effort?: ReasoningEffort | null) => {
      if (!conversationId) throw new Error('Conversation ID is missing.');
      setIsSubmitting(true);
      try {
        const reportContext = await reportCanvas.current?.capture();
        const accepted = await api.submitMessage(conversationId, {
          content,
          model_profile_id: modelProfileId ?? null,
          reasoning_effort: effort ?? null,
          ...(reportContext ? { power_bi_context: reportContext } : {}),
        });
        appendOptimisticMessage(accepted, content);
        await jobManager.registerJob(accepted.job_id);
        await queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists(orgId) });
      } finally {
        setIsSubmitting(false);
      }
    },
    [appendOptimisticMessage, conversationId, jobManager, orgId, queryClient],
  );

  const submitClarification = useCallback(
    async (messageId: string, answers: ClarificationAnswer[]) => {
      if (!conversationId) throw new Error('Conversation ID is missing.');
      setIsSubmitting(true);
      try {
        const accepted = await api.answerClarification(conversationId, messageId, { answers });
        await jobManager.registerJob(accepted.job_id);
        await queryClient.invalidateQueries({
          queryKey: queryKeys.conversations.messages(orgId, conversationId),
        });
        await queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists(orgId) });
      } finally {
        setIsSubmitting(false);
      }
    },
    [conversationId, jobManager, orgId, queryClient],
  );

  const submitFollowUp = useCallback(
    (question: string) => submit(question, selectedProfileId, reasoningEffort),
    [reasoningEffort, selectedProfileId, submit],
  );

  useEffect(() => {
    const state = location.state as PendingConversationState;
    if (!conversationId || !state?.pendingQuestion || pendingStarted.current) return;
    pendingStarted.current = true;
    const content = state.pendingQuestion;
    const modelProfileId = state.modelProfileId ?? null;
    const effort = state.reasoningEffort ?? null;
    navigate(location.pathname, { replace: true, state: null });
    void submit(content, modelProfileId, effort).catch((error) =>
      setInitialSubmitError(errorMessage(error)),
    );
  }, [conversationId, location.pathname, location.state, navigate, submit]);

  // Follow incoming text only while the reader has stayed near the bottom.
  const newestMessageId = messages.messages.at(-1)?.id;
  useLayoutEffect(() => {
    if (followScrollRef.current) scrollAnchorRef.current?.scrollIntoView({ behavior: 'instant' });
  }, [newestMessageId, activeRunningJob?.job.id, activeRunningJob?.answer?.text.length]);

  // Older pages are prepended above the reader; keep the visible messages where they were.
  const oldestMessageId = messages.messages[0]?.id;
  const prependAnchorRef = useRef<{ oldestId: string | undefined; height: number } | null>(null);
  const loadOlderMessages = useCallback(() => {
    const scroll = workspaceRef.current?.querySelector<HTMLElement>('.chat-main-scroll');
    prependAnchorRef.current = { oldestId: oldestMessageId, height: scroll?.scrollHeight ?? 0 };
    void messages.fetchNextPage();
  }, [messages, oldestMessageId]);
  useLayoutEffect(() => {
    const anchor = prependAnchorRef.current;
    if (!anchor || anchor.oldestId === oldestMessageId) return;
    prependAnchorRef.current = null;
    const scroll = workspaceRef.current?.querySelector<HTMLElement>('.chat-main-scroll');
    if (scroll) scroll.scrollTop += scroll.scrollHeight - anchor.height;
  }, [oldestMessageId]);

  useEffect(() => {
    if (!composerElement) return;
    const scroll = workspaceRef.current?.querySelector<HTMLElement>('.chat-main-scroll');
    if (!scroll) return;
    const trackScroll = () => {
      followScrollRef.current = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 80;
    };
    scroll.addEventListener('scroll', trackScroll, { passive: true });
    // The composer stays in layout; only match the message viewport's scrollbar gutter.
    const updateGutter = () => {
      composerElement.style.setProperty(
        '--conversation-scrollbar-width',
        `${scroll.offsetWidth - scroll.clientWidth}px`,
      );
    };
    updateGutter();
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
        updateGutter();
        // Charts can gain height after their trace loads, between text batches.
        if (followScrollRef.current) scroll.scrollTop = scroll.scrollHeight;
      });
    observer?.observe(scroll);
    const stream = workspaceRef.current?.querySelector<HTMLElement>('.chat-message-stream');
    if (stream) observer?.observe(stream);
    window.addEventListener('resize', updateGutter);
    return () => {
      observer?.disconnect();
      scroll.removeEventListener('scroll', trackScroll);
      window.removeEventListener('resize', updateGutter);
    };
  }, [composerElement]);

  if (!conversationId) {
    return (
      <PageError title="Conversation not found" message="The conversation identifier is missing." />
    );
  }
  if (conversation.isLoading || messages.isLoading) {
    return <PageLoading label="Loading conversation…" />;
  }
  if (conversation.isError) {
    return (
      <PageError
        title="Conversation unavailable"
        message="It may not exist in this workspace, or you may no longer have access."
        retry={() => void conversation.refetch()}
      />
    );
  }
  if (messages.isError && !messages.isFetchNextPageError) {
    return (
      <PageError
        title="Unable to load messages"
        message="The durable conversation exists, but its messages could not be loaded."
        retry={() => void messages.refetch()}
      />
    );
  }

  const sourceMap = new Map((dataSources.data ?? []).map((source) => [source.id, source]));

  const durableMessages = orderConversationTurns(messages.messages);
  const latestAssistantId = durableMessages.findLast((message) => message.role === 'assistant')?.id;
  // Questions from a paused analysis are not its answer; the job continues after them.
  const assistantJobIds = new Set(
    durableMessages
      .filter(
        (message) =>
          message.role === 'assistant' && message.job_id && !clarificationRequest(message),
      )
      .map((message) => message.job_id),
  );
  // A resumed job has two user messages (question, then answers); progress follows the latest.
  const latestUserMessageByJob = new Map(
    durableMessages
      .filter((message) => message.role === 'user' && message.job_id)
      .map((message) => [message.job_id, message.id]),
  );
  const jobsById = new Map(conversationJobs.map((entry) => [entry.job.id, entry]));
  const progressJob =
    conversationJobs.find(
      (entry) => entry.job.status === 'running' && !assistantJobIds.has(entry.job.id),
    ) ??
    conversationJobs.find(
      (entry) => entry.job.status === 'queued' && !assistantJobIds.has(entry.job.id),
    );
  const insertedJobs = new Set<string>();
  const lastMessage = durableMessages.at(-1);
  // Questions from a paused analysis close once it is cancelled or expires; a status not loaded
  // yet falls back to message order.
  const stillWaiting = (message: api.ConversationMessage) => {
    const job = message.job_id ? jobsById.get(message.job_id)?.job : undefined;
    return !resumesPausedAnalysis(message) || !job || isWaitingJobStatus(job.status);
  };
  // The newest questions can be answered until the conversation moves on.
  const awaitingAnswers =
    !progressJob &&
    lastMessage !== undefined &&
    clarificationRequest(lastMessage) !== null &&
    clarificationAnswers(durableMessages, lastMessage.id) === null &&
    stillWaiting(lastMessage);

  const messageTimeline = durableMessages.flatMap((message, index) => {
    const question =
      message.role === 'assistant'
        ? (durableMessages
            .slice(0, index)
            .findLast(
              (item) => item.role === 'user' && (!message.job_id || item.job_id === message.job_id),
            )?.content ??
          durableMessages.slice(0, index).findLast((item) => item.role === 'user')?.content ??
          conversation.data?.title)
        : undefined;
    const items = [
      <ConversationMessage
        key={message.id}
        message={message}
        question={question ?? undefined}
        queued={Boolean(
          message.job_id &&
          latestUserMessageByJob.get(message.job_id) === message.id &&
          message.job_id !== progressJob?.job.id &&
          jobsById.get(message.job_id)?.job.status === 'queued',
        )}
        senderName={user?.display_name?.trim() || user?.email || 'You'}
        onFollowUp={submitFollowUp}
        showSuggestions={message.id === latestAssistantId}
        followUpDisabled={isSubmitting}
        clarification={(() => {
          const request = clarificationRequest(message);
          if (!request) return undefined;
          const pausedJob = message.job_id ? jobsById.get(message.job_id)?.job : undefined;
          const paused = resumesPausedAnalysis(message);
          return {
            request,
            answered: clarificationAnswers(durableMessages, message.id),
            canAnswer: awaitingAnswers && message.id === lastMessage?.id,
            onSubmit: (answers: ClarificationAnswer[]) => submitClarification(message.id, answers),
            onCancel:
              paused && pausedJob && isWaitingJobStatus(pausedJob.status)
                ? () => jobManager.cancel(pausedJob.id)
                : undefined,
          };
        })()}
      />,
    ];
    if (
      message.role !== 'user' ||
      !message.job_id ||
      assistantJobIds.has(message.job_id) ||
      latestUserMessageByJob.get(message.job_id) !== message.id
    )
      return items;
    const entry = jobsById.get(message.job_id);
    if (!entry) return items;
    insertedJobs.add(entry.job.id);
    if (entry.job.id === progressJob?.job.id) {
      items.push(
        <AnalysisProgress
          key={`progress-${entry.job.id}`}
          managedJob={entry}
          onCancel={() => jobManager.cancel(entry.job.id)}
        />,
      );
    }
    if (entry.answer?.text) {
      items.push(
        <StreamingAnswer
          key={`draft-${entry.job.id}`}
          managedJob={entry}
          dataSourceNames={sourceNames}
        />,
      );
    }
    if (isTerminalJobStatus(entry.job.status) && entry.job.status !== 'succeeded') {
      items.push(<AnalysisFailure key={`failure-${entry.job.id}`} job={entry.job} />);
    }
    return items;
  });

  const unmatchedJobs = conversationJobs.filter(
    (entry) => !insertedJobs.has(entry.job.id) && !assistantJobIds.has(entry.job.id),
  );

  return (
    <div className="conversation-with-report">
    <div ref={workspaceRef} className="chat-workspace">
      <header className="conversation-heading">
        <h1>{conversation.data?.title?.trim() || 'Analysis'}</h1>
        {(conversation.data?.data_source_ids ?? []).some((id) => sourceMap.get(id)?.kind === 'powerbi') && <ReportLauncher
          sourceIds={(conversation.data?.data_source_ids ?? []).filter((id) => sourceMap.get(id)?.kind === 'powerbi')}
          onOpen={setSelectedReport} />}
        <ConversationActions
          key={conversationId}
          id={conversationId}
          title={conversation.data?.title ?? null}
          sources={(conversation.data?.data_source_ids ?? []).map((id) => ({
            id,
            name: sourceMap.get(id)?.name ?? 'Unavailable data source',
          }))}
          tableScope={conversation.data?.table_scope ?? []}
        />
      </header>

      <div className="chat-main-scroll">
        {initialSubmitError && (
          <div
            className="p-3 mb-4 bg-[var(--db-danger-soft)] border border-[var(--db-border-default)] rounded text-xs text-[var(--db-danger)]"
            role="alert"
          >
            <strong>Question was not submitted</strong>
            <p>{initialSubmitError}</p>
          </div>
        )}

        {/* Message Stream */}
        <div className="chat-message-stream" aria-label="Conversation messages">
          {durableMessages.length > 0 && (
            <LoadMoreSentinel
              hasMore={messages.hasNextPage}
              isLoading={messages.isFetchingNextPage}
              isError={messages.isFetchNextPageError}
              onLoadMore={loadOlderMessages}
              loadingLabel="Loading earlier messages…"
              endLabel={messages.data && messages.data.pages.length > 1 ? 'Start of conversation' : undefined}
            />
          )}
          {durableMessages.length ? (
            messageTimeline
          ) : (
            <PageState
              title="No messages yet"
              description="Submit a question to begin this analysis."
            />
          )}

          {progressJob && !insertedJobs.has(progressJob.job.id) && (
            <AnalysisProgress
              key={`progress-${progressJob.job.id}`}
              managedJob={progressJob}
              onCancel={() => jobManager.cancel(progressJob.job.id)}
            />
          )}

          {unmatchedJobs
            .filter((entry) => entry.answer?.text)
            .map((entry) => (
              <StreamingAnswer
                key={`draft-${entry.job.id}`}
                managedJob={entry}
                dataSourceNames={sourceNames}
              />
            ))}

          {unmatchedJobs
            .filter(
              (entry) => isTerminalJobStatus(entry.job.status) && entry.job.status !== 'succeeded',
            )
            .slice(-2)
            .map((entry) => (
              <AnalysisFailure key={`orphan-failure-${entry.job.id}`} job={entry.job} />
            ))}

          <div ref={scrollAnchorRef} className="conversation-scroll-anchor" />
        </div>
      </div>

      {/* The composer stays in layout outside the scrolling messages. */}
      <FollowUpChatComposer
        key={conversationId}
        containerRef={setComposerElement}
        onSubmit={submitFollowUp}
        dataSources={(dataSources.data ?? []).filter((s) => s.status === 'active')}
        selectedDataSourceIds={conversation.data?.data_source_ids ?? []}
        tableScope={conversation.data?.table_scope ?? []}
        onTableScopeChange={(tableScope) => {
          if (conversationId) updateTableScope.mutate({ id: conversationId, tableScope });
        }}
        status={
          updateTableScope.isError ? (
            <p className="chat-composer-error" role="alert">
              {updateTableScope.error?.message || 'Unable to change tables. Try again.'}
            </p>
          ) : undefined
        }
        onDataSourceIdsChange={() => {}}
        profiles={(profiles.data ?? []).filter((p) => p.enabled)}
        selectedProfileId={selectedProfileId}
        onProfileIdChange={setSelectedProfileId}
        fallbackProfileId={conversation.data?.model_profile_id}
        reasoningEffort={reasoningEffort}
        onReasoningEffortChange={setReasoningEffort}
        isSubmitting={isSubmitting}
        disabled={awaitingAnswers}
        placeholder={
          awaitingAnswers
            ? 'Answer the questions above to continue'
            : 'Ask a follow-up about this analysis…'
        }
        inputLabel="Ask a follow-up"
        dataSourceSelection="hidden"
      />
    </div>
    {selectedReport && <PowerBICanvas key={`${orgId}:${user?.id}:${selectedReport.id}`} binding={selectedReport} onClose={() => setSelectedReport(null)} ref={reportCanvas} />}
    </div>
  );
}

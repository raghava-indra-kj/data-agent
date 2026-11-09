import { apiClient, withAuthRefresh } from '../../api/client';
import type { components } from '../../api/generated/schema';
import { getLocalTimeZone } from '../../lib/datetime';

type S = components['schemas'];
export type Conversation = S['ConversationResponse'];
export type ConversationPage = S['ConversationPage'];
export type MessagePage = S['MessagePage'];
export type ConversationMessage = S['app__conversations__schemas__MessageResponse'];
export type ConversationCreate = S['ConversationCreate'];
export type MessageCreate = S['MessageCreate'];
export type MessageAccepted = S['MessageAcceptedResponse'];

export function listConversations(
  search: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<ConversationPage> {
  return withAuthRefresh(() => apiClient.GET('/api/v1/conversations', {
    params: { query: { search: search || undefined, cursor } },
    signal,
  }));
}

export function createConversation(body: ConversationCreate): Promise<Conversation> {
  return withAuthRefresh(() => apiClient.POST('/api/v1/conversations', { body }));
}

export function getConversation(id: string): Promise<Conversation> {
  return withAuthRefresh(() => apiClient.GET('/api/v1/conversations/{conversation_id}', {
    params: { path: { conversation_id: id } },
  }));
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
  return withAuthRefresh(() => apiClient.PATCH('/api/v1/conversations/{conversation_id}', {
    params: { path: { conversation_id: id } },
    body: { title },
  }));
}

export function updateTableScope(
  id: string,
  tableScope: S['SourceTableScope'][],
): Promise<Conversation> {
  return withAuthRefresh(() => apiClient.PUT('/api/v1/conversations/{conversation_id}/table-scope', {
    params: { path: { conversation_id: id } },
    body: { table_scope: tableScope },
  }));
}

/** Newest messages first; `cursor` continues toward older messages. Items are chronological. */
export function listMessages(
  id: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<MessagePage> {
  return withAuthRefresh(() => apiClient.GET('/api/v1/conversations/{conversation_id}/messages', {
    params: { path: { conversation_id: id }, query: { cursor } },
    signal,
  }));
}

export function submitMessage(id: string, body: MessageCreate): Promise<MessageAccepted> {
  const requestBody = { ...body, timezone: body.timezone ?? getLocalTimeZone() };
  return withAuthRefresh(() => apiClient.POST('/api/v1/conversations/{conversation_id}/messages', {
    params: { path: { conversation_id: id } },
    body: requestBody,
  }));
}

export async function deleteConversation(id: string): Promise<void> {
  await withAuthRefresh(() => apiClient.DELETE('/api/v1/conversations/{conversation_id}', {
    params: { path: { conversation_id: id } },
  }));
}

export async function deleteAllConversations(): Promise<void> {
  await withAuthRefresh(() => apiClient.DELETE('/api/v1/conversations'));
}

export function saveVerification(message: ConversationMessage, body: S['MessageVerificationUpdate']): Promise<ConversationMessage> {
  return withAuthRefresh(() => apiClient.PATCH('/api/v1/conversations/{conversation_id}/messages/{message_id}/verification', {
    params: { path: { conversation_id: message.conversation_id, message_id: message.id } }, body,
  }));
}

export function answerClarification(
  conversationId: string,
  messageId: string,
  body: S['ClarificationAnswers'],
): Promise<MessageAccepted> {
  return withAuthRefresh(() =>
    apiClient.POST(
      '/api/v1/conversations/{conversation_id}/messages/{message_id}/clarification-answers',
      { params: { path: { conversation_id: conversationId, message_id: messageId } }, body },
    ),
  );
}

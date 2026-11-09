import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authSession } from '../../auth/session-storage';
import { setApiOrganizationId } from '../../organizations/organization-store';
import { server } from '../../test/server';
import * as datetime from '../../lib/datetime';
import {
  createConversation,
  listConversations,
  listMessages,
  renameConversation,
  submitMessage,
  updateTableScope,
} from './conversation-api';

// Resolve fetch after MSW starts instead of capturing the original fetch during imports.
vi.mock('openapi-fetch', async (importOriginal) => {
  const actual = await importOriginal<typeof import('openapi-fetch')>();
  return { ...actual, default: (options: Parameters<typeof actual.default>[0]) => actual.default({ ...options, fetch: (...args: Parameters<typeof fetch>) => globalThis.fetch(...args) }) };
});

beforeEach(() => {
  authSession.write({ access_token: 'a', refresh_token: 'r', token_type: 'bearer', expires_in: 900 });
  setApiOrganizationId('org-1');
});

describe('conversation API', () => {
  it('saves only the chat title through the scoped conversation endpoint', async () => {
    server.use(http.patch('http://localhost:12201/api/v1/conversations/c1', async ({ request }) => {
      expect(request.headers.get('x-organization-id')).toBe('org-1');
      expect(await request.json()).toEqual({ title: 'Saved analysis' });
      return HttpResponse.json({ id: 'c1', title: 'Saved analysis' });
    }));
    await expect(renameConversation('c1', 'Saved analysis')).resolves.toMatchObject({ id: 'c1', title: 'Saved analysis' });
  });
  it('saves the conversation table selection through its own endpoint', async () => {
    const scope = [{ data_source_id: 's1', mode: 'selected' as const, tables: [{ schema: 'dbo', name: 'orders' }] }];
    server.use(http.put('http://localhost:12201/api/v1/conversations/c1/table-scope', async ({ request }) => {
      expect(request.headers.get('x-organization-id')).toBe('org-1');
      expect(await request.json()).toEqual({ table_scope: scope });
      return HttpResponse.json({ id: 'c1', table_scope: scope });
    }));
    await expect(updateTableScope('c1', scope)).resolves.toMatchObject({ id: 'c1', table_scope: scope });
  });
  it('creates a conversation with multiple datasource identities intact', async () => {
    server.use(http.post('http://localhost:12201/api/v1/conversations', async ({ request }) => {
      expect(request.headers.get('x-organization-id')).toBe('org-1');
      const body = await request.json() as { data_source_ids: string[]; model_profile_id: string | null };
      expect(body.data_source_ids).toEqual(['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222']);
      expect(body.model_profile_id).toBeNull();
      return HttpResponse.json({
        id: '33333333-3333-4333-8333-333333333333', organization_id: 'org-1', title: 'Revenue', created_by: 'u1',
        model_profile_id: null, data_source_ids: body.data_source_ids, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z',
      }, { status: 201 });
    }));
    const result = await createConversation({ data_source_ids: ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'], model_profile_id: null, title: 'Revenue' });
    expect(result.data_source_ids).toHaveLength(2);
  });

  it('submits a question as an immediate durable message/job pair', async () => {
    const timezone = vi.spyOn(datetime, 'getLocalTimeZone').mockReturnValue('Asia/Kolkata');
    server.use(http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
      expect(await request.json()).toEqual({ content: 'Why did revenue fall?', model_profile_id: null, timezone: 'Asia/Kolkata' });
      return HttpResponse.json({ message_id: 'm1', job_id: 'j1' }, { status: 202 });
    }));
    await expect(submitMessage('c1', { content: 'Why did revenue fall?', model_profile_id: null })).resolves.toEqual({ message_id: 'm1', job_id: 'j1' });
    timezone.mockRestore();
  });

  it('preserves an explicitly supplied timezone', async () => {
    server.use(http.post('http://localhost:12201/api/v1/conversations/c1/messages', async ({ request }) => {
      expect(await request.json()).toEqual({ content: 'What time is it?', timezone: 'America/New_York' });
      return HttpResponse.json({ message_id: 'm1', job_id: 'j1' }, { status: 202 });
    }));
    await submitMessage('c1', { content: 'What time is it?', timezone: 'America/New_York' });
  });

  it('loads durable messages independently of browser job state', async () => {
    server.use(http.get('http://localhost:12201/api/v1/conversations/c1/messages', () => HttpResponse.json({ items: [
      { id: 'm1', conversation_id: 'c1', role: 'user', content: 'Question', job_id: 'j1', metadata: {}, created_at: '2026-08-24T12:00:00Z' },
      { id: 'm2', conversation_id: 'c1', role: 'assistant', content: '**Answer**', job_id: 'j1', metadata: {}, created_at: '2026-08-24T12:00:03Z' },
    ], next_cursor: null, has_more: false })));
    const page = await listMessages('c1');
    expect(page.items.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(page.has_more).toBe(false);
  });

  it('passes the opaque cursor and search to the paged endpoints', async () => {
    const seen: string[] = [];
    server.use(
      http.get('http://localhost:12201/api/v1/conversations', ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json({ items: [], next_cursor: null, has_more: false });
      }),
      http.get('http://localhost:12201/api/v1/conversations/c1/messages', ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json({ items: [], next_cursor: null, has_more: false });
      }),
    );
    await listConversations('rev', 'next-token');
    await listMessages('c1', 'older-token');
    await listConversations('');
    expect(seen).toEqual(['?search=rev&cursor=next-token', '?cursor=older-token', '']);
  });
});

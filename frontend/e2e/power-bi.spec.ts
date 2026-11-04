import { expect, test } from '@playwright/test';

test('report opens on click, expands alongside the conversation and closes explicitly', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 940 });
  const timestamp = '2026-11-04T00:00:00Z';
  let embeds = 0;
  await page.addInitScript(() =>
    sessionStorage.setItem(
      'db-assistant.auth.v1',
      JSON.stringify({
        access_token: 'mock',
        refresh_token: 'mock',
        token_type: 'bearer',
        expires_in: 900,
      }),
    ),
  );
  await page.route('https://app.powerbi.com/**', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<html><body style="font-family:system-ui;padding:32px;background:#fafafa"><h2>Backlog report</h2><p>Power BI frame test fixture</p></body></html>',
    }),
  );
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = [];
    if (path.endsWith('/auth/me'))
      json = {
        id: 'user',
        email: 'test@example.com',
        display_name: 'Test User',
        is_active: true,
        created_at: timestamp,
        updated_at: timestamp,
      };
    else if (path.endsWith('/organizations'))
      json = [{ id: 'org', name: 'Test workspace', role: 'owner' }];
    else if (path.endsWith('/data-sources'))
      json = [
        {
          id: 'source',
          name: 'Backlog',
          kind: 'powerbi',
          display_type: 'powerbi',
          status: 'active',
          config: {},
        },
      ];
    else if (path.endsWith('/power-bi/features'))
      json = { enabled: true, configured: true, embedding_enabled: true };
    else if (path.endsWith('/power-bi/connections'))
      json = [
        {
          id: 'connection',
          display_name: 'Test Microsoft account',
          tenant_id: 'tenant',
          status: 'connected',
        },
      ];
    else if (path.endsWith('/power-bi/reports'))
      json = [
        {
          id: 'binding',
          report_id: 'report',
          data_source_id: 'source',
          name: 'Operations backlog',
          web_url: '',
          embedding_enabled: true,
        },
      ];
    else if (path.endsWith('/embed-config')) {
      embeds++;
      json = {
        report_id: 'report',
        embed_url: 'https://app.powerbi.com/reportEmbed?reportId=report',
        access_token: 'test-token',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
        token_type: 'Aad',
      };
    } else if (path.endsWith('/conversations') || path.endsWith('/messages'))
      json = { items: [], has_more: false, next_cursor: null };
    else if (path.endsWith('/conversations/conversation'))
      json = {
        id: 'conversation',
        organization_id: 'org',
        title: 'Backlog analysis',
        data_source_ids: ['source'],
        table_scope: [],
        model_profile_id: null,
        created_by: 'user',
        created_at: timestamp,
        updated_at: timestamp,
      };
    return route.fulfill({ json });
  });
  await page.goto('/conversations/conversation');
  const canvas = page.getByRole('complementary', { name: 'Power BI report canvas' });
  await expect(page.getByRole('heading', { name: 'Backlog analysis' })).toBeVisible();
  await expect(canvas).toHaveCount(0);
  expect(embeds).toBe(0);
  const composer = page.getByRole('textbox', { name: 'Ask a follow-up' });
  await composer.fill('Which backlog orders need attention?');
  await page.getByRole('button', { name: 'Power BI', exact: true }).click();
  await page.getByRole('button', { name: 'Operations backlog', exact: true }).click();
  await expect(canvas).toBeVisible();
  await expect.poll(() => embeds).toBe(1);
  const initial = await canvas.boundingBox();
  await page.getByRole('button', { name: 'Expand report' }).click();
  const expanded = await canvas.boundingBox();
  expect(expanded!.width).toBeGreaterThan(initial!.width);
  await expect(composer).toBeVisible();
  await expect(composer).toHaveValue('Which backlog orders need attention?');
  await page.keyboard.press('Escape');
  await expect(canvas).toBeVisible();
  expect(embeds).toBe(1);
  await page.screenshot({ path: 'test-results/power-bi-canvas.png', fullPage: true });
  await page.getByRole('button', { name: 'Close report' }).click();
  await expect(canvas).toHaveCount(0);
  await expect(composer).toHaveValue('Which backlog orders need attention?');
});

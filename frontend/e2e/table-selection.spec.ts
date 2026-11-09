import { expect, test } from '@playwright/test';

const timestamp = '2026-10-08T00:00:00Z';
const source = {
  id: 'source-1',
  organization_id: 'org-1',
  name: 'Warehouse',
  kind: 'postgres',
  display_type: 'postgres',
  status: 'active',
  config: {},
  created_by: 'user-1',
  last_tested_at: null,
  last_error_code: null,
  created_at: timestamp,
  updated_at: timestamp,
  active_file: null,
};

for (const width of [1280, 390]) {
  test(`table selection supports keyboard navigation and fits a ${width}px screen`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(() =>
      sessionStorage.setItem(
        'db-assistant.auth.v1',
        JSON.stringify({
          access_token: 'mock-access',
          refresh_token: 'mock-refresh',
          token_type: 'bearer',
          expires_in: 900,
        }),
      ),
    );
    // Every API request is mocked: no real credentials, user records, or analytical jobs.
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      if (path.endsWith('/auth/me'))
        return route.fulfill({
          json: {
            id: 'user-1',
            email: 'tester@example.com',
            display_name: 'Tester',
            is_active: true,
            created_at: timestamp,
            updated_at: timestamp,
          },
        });
      if (path.endsWith('/organizations'))
        return route.fulfill({
          json: [
            {
              id: 'org-1',
              name: 'Test workspace',
              role: 'owner',
              created_at: timestamp,
              updated_at: timestamp,
            },
          ],
        });
      if (path.endsWith('/data-sources')) return route.fulfill({ json: [source] });
      if (path.endsWith('/models/profiles'))
        return route.fulfill({
          json: [
            {
              id: 'profile-1',
              organization_id: 'org-1',
              connection_id: 'connection-1',
              display_name: 'Test model',
              model_name: 'test-model',
              settings: {},
              enabled: true,
              is_default: true,
              reasoning_efforts: ['low', 'medium', 'high'],
              default_reasoning_effort: 'medium',
              created_at: timestamp,
              updated_at: timestamp,
            },
          ],
        });
      if (path.endsWith('/instructions'))
        return route.fulfill({
          json: [
            {
              id: 'template-1',
              name: 'Weekly summary',
              command: 'weekly',
              enabled: true,
              description: 'Summarize the week',
              content: 'Write a summary.',
            },
          ],
        });
      if (path.endsWith('/tables'))
        return route.fulfill({
          json: {
            knowledge_version_id: 'version-1',
            next_cursor: null,
            items: [
              { schema: 'public', name: 'orders', object_type: 'table', column_count: 12 },
              {
                schema: 'reporting',
                name: 'RegionalPerformanceSummaryWithAnExtendedName',
                object_type: 'view',
                column_count: 4,
              },
              ...Array.from({ length: 24 }, (_, index) => ({
                schema: 'public',
                name: `APJ_Backlog_Analysis_${String(index + 1).padStart(2, '0')}`,
                object_type: index % 3 === 0 ? 'view' : 'table',
                column_count: 10 + index * 3,
              })),
            ],
          },
        });
      // The chat sidebar reads paged conversations.
      if (new URL(route.request().url()).pathname.endsWith('/conversations'))
        return route.fulfill({ json: { items: [], next_cursor: null, has_more: false } });
      return route.fulfill({ json: [] });
    });
    await page.goto('/ask');
    const composer = page.getByRole('region', { name: 'Query composer' });
    await expect(composer.getByRole('button')).toHaveCount(4);
    await expect(
      page.getByText('Explore a trend, compare results, or ask a question in your own words.'),
    ).toHaveCount(0);
    const card = composer.locator('.chat-composer-card');
    expect((await card.boundingBox())!.height).toBeLessThan(width < 600 ? 140 : 115);
    await card.screenshot({
      path: test.info().outputPath(`composer-${width}.png`),
      animations: 'disabled',
    });
    if (width > 600) {
      await composer.getByRole('button', { name: 'Data scope', exact: true }).hover();
      await expect(page.getByRole('tooltip')).toContainText('Warehouse');
    }
    await composer.getByRole('button', { name: 'Model settings' }).click();
    const settings = page.getByRole('dialog', { name: 'Model settings' });
    await settings.getByRole('button', { name: /Reasoning effort/ }).click();
    await page.getByRole('option', { name: 'High', exact: true }).click();
    await expect(settings.getByRole('button', { name: /Reasoning effort/ })).toContainText('High');
    await page.screenshot({
      path: test.info().outputPath(`model-settings-${width}.png`),
      animations: 'disabled',
    });
    await page.keyboard.press('Escape');
    await expect(composer.getByRole('button', { name: 'Model settings' })).toBeFocused();
    await composer.getByRole('button', { name: 'Templates' }).click();
    await page.getByRole('searchbox', { name: 'Search templates' }).fill('weekly');
    await page.getByRole('option', { name: 'Weekly summary' }).click();
    await expect(composer.locator('.composer-icon-dot')).toHaveCount(2);
    await expect(composer.getByRole('textbox')).toHaveValue('');
    await page.getByRole('button', { name: 'Data scope', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('radio', { name: 'Choose tables' }).focus();
    await page.keyboard.press('Space');
    const orders = dialog.getByRole('checkbox', { name: /orders/ });
    await orders.focus();
    await page.keyboard.press('Space');
    await expect(orders).toBeChecked();
    await expect(dialog.getByRole('radio', { name: 'Choose tables' })).toBeChecked();
    const bounds = await dialog.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    const footer = dialog.locator('.composer-popover-footer');
    const footerBefore = await footer.boundingBox();
    const catalog = dialog.locator('.table-scope-catalog');
    await catalog.evaluate((node) => {
      node.scrollTop = node.scrollHeight;
    });
    // Ignore subpixel motion during the modal's opening animation.
    expect(Math.abs((await footer.boundingBox())!.y - footerBefore!.y)).toBeLessThan(3);
    await expect(dialog.getByRole('button', { name: 'Done' })).toBeInViewport();
    await catalog.evaluate((node) => {
      node.scrollTop = 0;
    });
    await page.screenshot({
      path: test.info().outputPath(`table-picker-${width}.png`),
      animations: 'disabled',
    });
    await dialog.getByRole('button', { name: 'Done' }).click();
    await expect(page.getByRole('button', { name: 'Data scope', exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Data scope', exact: true }).click();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Data scope', exact: true })).toBeFocused();
    await page.getByRole('button', { name: 'Data scope', exact: true }).click();
    await dialog.getByRole('checkbox', { name: /orders/ }).uncheck();
    await dialog
      .getByRole('checkbox', { name: /RegionalPerformanceSummaryWithAnExtendedName/ })
      .check();
    await dialog.getByRole('button', { name: 'Done' }).click();
    const longNameTrigger = page.getByRole('button', {
      name: 'Data scope',
      exact: true,
    });
    await expect(longNameTrigger).toBeVisible();
    const chipBounds = await longNameTrigger.boundingBox();
    expect(chipBounds!.x + chipBounds!.width).toBeLessThanOrEqual(width);
  });
}

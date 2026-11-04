import { createRef } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PowerBICanvas, type ReportCanvasHandle } from './PowerBICanvas';
const mocks = vi.hoisted(() => ({
  embed: vi.fn(),
  reset: vi.fn(),
  config: vi.fn(),
  renew: vi.fn(),
  events: new Map<string, () => void>(),
}));
vi.mock('./api', () => ({ embedConfig: mocks.config }));
vi.mock('powerbi-client', () => ({
  service: {
    Service: class {
      embed = mocks.embed;
      reset = mocks.reset;
    },
  },
  factories: {},
  models: {
    TokenType: { Aad: 0 },
    Permissions: { Read: 0 },
    ViewMode: { View: 0 },
    BackgroundType: { Transparent: 1 },
  },
}));
const binding = {
  id: 'binding',
  data_source_id: 'source',
  report_id: 'report',
  name: 'Backlog',
  web_url: '',
  embedding_enabled: true,
};
beforeEach(() => {
  mocks.events.clear();
  mocks.embed.mockClear();
  mocks.reset.mockClear();
  mocks.config.mockClear();
  mocks.config.mockResolvedValue({
    report_id: 'report',
    embed_url: 'https://app.powerbi.com/reportEmbed',
    access_token: 'test-only-token',
    expires_at: new Date(Date.now() + 3600_000).toISOString(),
  });
  mocks.embed.mockReturnValue({
    on: (event: string, callback: () => void) => {
      mocks.events.set(event, callback);
    },
    setAccessToken: mocks.renew,
  });
});
it('keeps one embed instance through rerenders and expansion; disposes on close', async () => {
  const close = vi.fn();
  const ref = createRef<ReportCanvasHandle>();
  const view = render(<PowerBICanvas binding={binding} onClose={close} ref={ref} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  view.rerender(<PowerBICanvas binding={{ ...binding }} onClose={close} ref={ref} />);
  await userEvent.click(screen.getByRole('button', { name: 'Expand report' }));
  expect(mocks.embed).toHaveBeenCalledTimes(1);
  expect(mocks.config).toHaveBeenCalledTimes(1);
  expect(await ref.current?.capture()).toMatchObject({
    mode: 'model',
    report_binding_id: 'binding',
  });
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
  await userEvent.click(screen.getByRole('button', { name: 'Close report' }));
  expect(close).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(mocks.reset).toHaveBeenCalledTimes(1);
});
it('does not submit a filtered question before the report has loaded', async () => {
  const ref = createRef<ReportCanvasHandle>();
  render(<PowerBICanvas binding={binding} onClose={() => {}} ref={ref} />);
  await userEvent.selectOptions(screen.getByLabelText('Power BI question scope'), 'report_view');
  await expect(ref.current?.capture()).rejects.toThrow('Wait for the report');
});

it('renews the token when the tab wakes without recreating the report', async () => {
  const view = render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 3600_000);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  await act(async () => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(mocks.renew).toHaveBeenCalledWith('test-only-token');
  expect(mocks.embed).toHaveBeenCalledTimes(1);
  view.unmount();
});

it('removes the report immediately when Microsoft is disconnected', async () => {
  render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  await act(async () => {
    window.dispatchEvent(new Event('power-bi-disconnected'));
  });
  expect(mocks.reset).toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('Microsoft account disconnected');
});

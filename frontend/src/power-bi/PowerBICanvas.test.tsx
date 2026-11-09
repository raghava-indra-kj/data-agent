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
  fullscreen: vi.fn(),
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
    LayoutType: { Custom: 2 },
    DisplayOption: { FitToWidth: 1 },
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
    updateSettings: vi.fn().mockResolvedValue(undefined),
    fullscreen: mocks.fullscreen,
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
  await userEvent.click(screen.getByRole('button', { name: /Power BI question scope/ }));
  await userEvent.click(await screen.findByRole('option', { name: 'Page filters & slicers' }));
  await expect(ref.current?.capture()).rejects.toThrow('Wait for the report');
});

it('keeps a sized embed mounted and explains the wait until visuals have rendered', async () => {
  const { container } = render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  const host = container.querySelector('.pbi-embed-host');
  expect(screen.getByRole('status')).toHaveTextContent('Loading your Power BI report');
  expect(screen.getByRole('status')).toHaveTextContent('This may take a little while');
  expect(host).not.toHaveAttribute('hidden');
  expect(host).toHaveAttribute('aria-busy', 'true');
  expect(host).toHaveAttribute('inert');
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  await act(async () => mocks.events.get('loaded')?.());
  expect(screen.getByRole('status')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Full screen' })).toBeEnabled();
  await act(async () => mocks.events.get('rendered')?.());
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(container.querySelector('.pbi-embed-host')).toBe(host);
  expect(host).toHaveAttribute('aria-busy', 'false');
  expect(host).not.toHaveAttribute('inert');
  expect(mocks.embed).toHaveBeenCalledTimes(1);
});

it('replaces loading with an error and restores it on retry, ignoring stale events', async () => {
  render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  const staleRendered = mocks.events.get('rendered');
  const staleLoaded = mocks.events.get('loaded');
  await act(async () => mocks.events.get('error')?.());
  expect(screen.getByRole('alert')).toHaveTextContent('Unable to load or renew this report');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  await act(async () => {
    staleLoaded?.();
    staleRendered?.();
  });
  expect(screen.getByRole('button', { name: 'Full screen' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry report' }));
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('status')).toHaveTextContent('Loading your Power BI report');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await act(async () => staleRendered?.());
  expect(screen.getByRole('status')).toBeInTheDocument();
  await act(async () => mocks.events.get('rendered')?.());
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('identifies the unsupported page filter when capturing a report view', async () => {
  const page = {
    name: 'Page1',
    displayName: 'Backlog',
    getFilters: async () => [{
      filterType: 4,
      target: { table: 'Orders', column: 'Date' },
    }],
    getVisuals: async () => [],
  };
  mocks.embed.mockReturnValue({
    on: (event: string, callback: () => void) => mocks.events.set(event, callback),
    updateSettings: vi.fn().mockResolvedValue(undefined),
    getActivePage: async () => page,
    getFilters: async () => [],
  });
  const ref = createRef<ReportCanvasHandle>();
  render(<PowerBICanvas binding={binding} onClose={() => {}} ref={ref} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  await act(async () => mocks.events.get('loaded')?.());
  await userEvent.click(screen.getByRole('button', { name: /Power BI question scope/ }));
  await userEvent.click(await screen.findByRole('option', { name: 'Page filters & slicers' }));
  await expect(ref.current?.capture()).rejects.toThrow(
    'Page filter (Orders.Date): unsupported relative date filter type',
  );
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

it('toggles focus mode every time and always shows the restore control', async () => {
  const { container } = render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  const canvas = container.querySelector('.pbi-canvas');
  expect(canvas).not.toHaveClass('is-expanded');
  await userEvent.click(screen.getByRole('button', { name: 'Expand report' }));
  expect(canvas).toHaveClass('is-expanded');
  await userEvent.click(screen.getByRole('button', { name: 'Restore report size' }));
  expect(canvas).not.toHaveClass('is-expanded');
  await userEvent.click(screen.getByRole('button', { name: 'Expand report' }));
  await userEvent.keyboard('{Escape}');
  expect(canvas).not.toHaveClass('is-expanded');
});

it('enters Power BI full screen only once the report has loaded', async () => {
  render(<PowerBICanvas binding={binding} onClose={() => {}} ref={null} />);
  await waitFor(() => expect(mocks.embed).toHaveBeenCalledTimes(1));
  const button = screen.getByRole('button', { name: 'Full screen' });
  expect(button).toBeDisabled();
  await act(async () => {
    mocks.events.get('loaded')?.();
  });
  await userEvent.click(button);
  expect(mocks.fullscreen).toHaveBeenCalledTimes(1);
});

import { Button } from '@heroui/react';
import { ChartColumn, Fullscreen, Maximize2, Minimize2, RefreshCw, X } from 'lucide-react';
import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import type { Report, service } from 'powerbi-client';
import { SingleSelect } from '../components/SingleSelect';
import { embedConfig, type PowerBIReport, type ReportContext } from './api';
import { captureReportContext } from './report-context';
import { TipButton } from './TipButton';
import './power-bi.css';

const MIN_WIDTH = 35;
const MAX_WIDTH = 85;
const SCOPE_OPTIONS = [
  { value: 'model', label: 'Entire model' },
  { value: 'report_view', label: 'Page filters & slicers' },
] as const;

export type ReportCanvasHandle = { capture(): Promise<ReportContext | undefined> };

export function PowerBICanvas({
  binding,
  onClose,
  ref,
}: {
  binding: PowerBIReport;
  onClose(): void;
  ref: Ref<ReportCanvasHandle>;
}) {
  const host = useRef<HTMLDivElement>(null);
  const embedded = useRef<Report | null>(null);
  const [ready, setReady] = useState(false);
  const [hasRendered, setHasRendered] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [width, setWidth] = useState(55);
  const [attempt, setAttempt] = useState(0);
  const [resizing, setResizing] = useState(false);
  const [scope, setScope] = useState<'model' | 'report_view'>('model');
  const selectionChanged = useRef(false);
  const capture = useCallback(async () => {
    if (scope === 'model')
      return {
        report_binding_id: binding.id,
        page_name: '',
        page_display_name: '',
        captured_at: new Date().toISOString(),
        mode: 'model' as const,
        filters: [],
        unsupported: [],
      };
    if (!ready || !embedded.current)
      throw new Error('Wait for the report to load, or choose Entire model.');
    if (selectionChanged.current)
      throw new Error(
        'Chart selections cannot be captured reliably. Choose Entire model, or reload the report and use page filters and slicers.',
      );
    const context = await captureReportContext(embedded.current, binding.id);
    if (context.unsupported?.length) {
      const issues = context.unsupported.slice(0, 5).join('; ');
      const remainder = context.unsupported.length - 5;
      throw new Error(
        `Cannot use the current page filters: ${issues}${remainder > 0 ? `; and ${remainder} more` : ''}. ` +
        'Adjust the filters or choose Entire model.',
      );
    }
    return context;
  }, [binding.id, ready, scope]);
  useImperativeHandle(ref, () => ({ capture }), [capture]);

  useEffect(() => {
    if (!expanded) return;
    const collapse = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', collapse);
    return () => window.removeEventListener('keydown', collapse);
  }, [expanded]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let sdk: service.Service | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let renewing = false;
    let expiresAt = 0;
    let loaded = false;
    let layout: Parameters<Report['updateSettings']>[0] | undefined;
    let refit: ReturnType<typeof setTimeout> | undefined;
    // Power BI only re-fits its page on window resize, so a container that changes size
    // (expand, collapse, splitter drag, sidebar toggle) must re-apply the layout itself.
    const observer = new ResizeObserver(() => {
      clearTimeout(refit);
      refit = setTimeout(() => {
        if (disposed || !loaded || !layout) return;
        embedded.current?.updateSettings(layout).catch(() => undefined);
      }, 120);
    });
    observer.observe(element);
    setError(null);
    setReady(false);
    setHasRendered(false);
    selectionChanged.current = false;
    const fail = () => {
      if (!disposed) {
        clearTimeout(timer);
        sdk?.reset(element);
        embedded.current = null;
        setError(
          'Unable to load or renew this report. Check Microsoft access, reconnect if needed, then retry.',
        );
        setReady(false);
        setHasRendered(false);
      }
    };
    const renew = async () => {
      if (disposed || renewing || !embedded.current) return;
      renewing = true;
      try {
        const config = await embedConfig(binding.id);
        if (disposed || !embedded.current) return;
        await embedded.current.setAccessToken(config.access_token);
        expiresAt = Date.parse(config.expires_at);
        timer = setTimeout(() => void renew(), Math.max(10_000, expiresAt - Date.now() - 120_000));
      } catch {
        fail();
      } finally {
        renewing = false;
      }
    };
    const visibility = () => {
      if (document.visibilityState === 'visible' && Date.now() > expiresAt - 120_000) {
        clearTimeout(timer);
        void renew();
      }
    };
    const disconnected = () => {
      disposed = true;
      clearTimeout(timer);
      sdk?.reset(element);
      embedded.current = null;
      setReady(false);
      setHasRendered(false);
      setError('Microsoft account disconnected. Reconnect before opening this report again.');
    };
    window.addEventListener('power-bi-disconnected', disconnected);
    void (async () => {
      try {
        // React StrictMode replays effects in development. Let its first cleanup cancel
        // startup before requesting a delegated token or creating a second iframe.
        await Promise.resolve();
        if (disposed) return;
        const [pbi, config] = await Promise.all([
          import('powerbi-client'),
          embedConfig(binding.id),
        ]);
        if (disposed) return;
        sdk = new pbi.service.Service(
          pbi.factories.hpmFactory,
          pbi.factories.wpmpFactory,
          pbi.factories.routerFactory,
        );
        const report = sdk.embed(element, {
          type: 'report',
          id: config.report_id,
          embedUrl: config.embed_url,
          accessToken: config.access_token,
          tokenType: pbi.models.TokenType.Aad,
          permissions: pbi.models.Permissions.Read,
          viewMode: pbi.models.ViewMode.View,
          settings: {
            panes: { filters: { visible: true }, pageNavigation: { visible: true } },
            background: pbi.models.BackgroundType.Transparent,
            layoutType: pbi.models.LayoutType.Custom,
            customLayout: { displayOption: pbi.models.DisplayOption.FitToWidth },
          },
        }) as Report;
        layout = {
          layoutType: pbi.models.LayoutType.Custom,
          customLayout: { displayOption: pbi.models.DisplayOption.FitToWidth },
        };
        embedded.current = report;
        report.on('loaded', () => {
          if (disposed || embedded.current !== report) return;
          loaded = true;
          setReady(true);
        });
        // SDK APIs are ready at loaded; keep the loading state until visuals are visible.
        report.on('rendered', () => {
          if (disposed || embedded.current !== report) return;
          setHasRendered(true);
        });
        report.on('error', fail);
        report.on('dataSelected', () => {
          selectionChanged.current = true;
        });
        expiresAt = Date.parse(config.expires_at);
        timer = setTimeout(() => void renew(), Math.max(10_000, expiresAt - Date.now() - 120_000));
        document.addEventListener('visibilitychange', visibility);
      } catch {
        fail();
      }
    })();
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(refit);
      observer.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('power-bi-disconnected', disconnected);
      embedded.current = null;
      sdk?.reset(element);
    };
  }, [binding.id, attempt]);

  return (
    <aside
      className={`pbi-canvas ${expanded ? 'is-expanded' : ''} ${resizing ? 'is-resizing' : ''}`}
      style={{ flexBasis: `${expanded ? 100 : width}%` }}
      aria-label="Power BI report canvas"
    >
      <div
        role="separator"
        aria-label="Resize report canvas"
        aria-orientation="vertical"
        tabIndex={0}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        aria-valuenow={width}
        className="pbi-resize"
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            setExpanded(false);
            setWidth((value) =>
              Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value + (event.key === 'ArrowLeft' ? 5 : -5))),
            );
          }
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setResizing(true);
        }}
        onPointerMove={(event) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          const rect = event.currentTarget.parentElement?.parentElement?.getBoundingClientRect();
          if (rect) {
            setExpanded(false);
            setWidth(
              Math.min(
                MAX_WIDTH,
                Math.max(MIN_WIDTH, ((rect.right - event.clientX) / rect.width) * 100),
              ),
            );
          }
        }}
        onPointerUp={(event) => {
          event.currentTarget.releasePointerCapture(event.pointerId);
          setResizing(false);
        }}
        onPointerCancel={() => setResizing(false)}
      />
      <header className="pbi-canvas-heading">
        <div className="pbi-heading-main">
          <ChartColumn className="pbi-mark" size={18} aria-hidden="true" />
          <strong title={binding.name}>{binding.name}</strong>
        </div>
        <div className="pbi-actions">
          <SingleSelect<'model' | 'report_view'>
            compact
            className="pbi-scope-select"
            label="Power BI question scope"
            value={scope}
            onChange={setScope}
            options={SCOPE_OPTIONS}
          />
          <TipButton
            variant="tertiary"
            label={expanded ? 'Restore report size' : 'Expand report'}
            aria-pressed={expanded}
            onPress={() => setExpanded((value) => !value)}
          >
            {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </TipButton>
          <TipButton
            variant="tertiary"
            label="Full screen"
            isDisabled={!ready}
            onPress={() => embedded.current?.fullscreen()}
          >
            <Fullscreen size={16} />
          </TipButton>
          <TipButton variant="tertiary" label="Close report" onPress={onClose}>
            <X size={16} />
          </TipButton>
        </div>
      </header>
      {scope === 'report_view' && (
        <p className="pbi-scope-note">
          Captured when you send. Chart-specific filters and cross-highlights are excluded.
        </p>
      )}
      <div className="pbi-canvas-body">
        <div
          ref={host}
          className="pbi-embed-host"
          hidden={Boolean(error)}
          aria-busy={!hasRendered && !error}
          inert={!hasRendered || Boolean(error)}
        />
        {error ? (
          <div role="alert" className="pbi-canvas-message">
            <p>{error}</p>
            <Button variant="secondary" onPress={() => setAttempt((value) => value + 1)}>
              <RefreshCw size={14} />
              Retry report
            </Button>
          </div>
        ) : !hasRendered ? (
          <div role="status" aria-live="polite" aria-atomic="true" className="pbi-canvas-loading">
            <div className="pbi-canvas-loading-content">
              <div className="pbi-canvas-loading-icon" aria-hidden="true">
                <span className="pbi-canvas-loading-spinner" />
                <ChartColumn size={26} strokeWidth={1.8} />
              </div>
              <h2>Loading your Power BI report</h2>
              <p>This may take a little while, especially for larger reports.</p>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

import { Button } from '@heroui/react';
import { Maximize2, Minimize2, RefreshCw, X } from 'lucide-react';
import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import type { Report, service } from 'powerbi-client';
import { embedConfig, type PowerBIReport, type ReportContext } from './api';
import { captureReportContext } from './report-context';
import './power-bi.css';

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
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [width, setWidth] = useState(55);
  const [attempt, setAttempt] = useState(0);
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
    if (context.unsupported?.length)
      throw new Error(
        'This report has filters we cannot capture. Choose Entire model to continue.',
      );
    return context;
  }, [binding.id, ready, scope]);
  useImperativeHandle(ref, () => ({ capture }), [capture]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let sdk: service.Service | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let renewing = false;
    let expiresAt = 0;
    setError(null);
    setReady(false);
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
          },
        }) as Report;
        embedded.current = report;
        report.on('loaded', () => {
          if (!disposed) setReady(true);
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
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('power-bi-disconnected', disconnected);
      embedded.current = null;
      sdk?.reset(element);
    };
  }, [binding.id, attempt]);

  return (
    <aside
      className={`pbi-canvas ${expanded ? 'is-expanded' : ''}`}
      style={{ flexBasis: `${expanded ? 72 : width}%` }}
      aria-label="Power BI report canvas"
    >
      <div
        role="separator"
        aria-label="Resize report canvas"
        aria-orientation="vertical"
        tabIndex={0}
        aria-valuemin={35}
        aria-valuemax={72}
        aria-valuenow={expanded ? 72 : width}
        className="pbi-resize"
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            setExpanded(false);
            setWidth((value) =>
              Math.min(72, Math.max(35, value + (event.key === 'ArrowLeft' ? 5 : -5))),
            );
          }
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          const rect = event.currentTarget.parentElement?.parentElement?.getBoundingClientRect();
          if (rect) {
            setExpanded(false);
            setWidth(Math.min(72, Math.max(35, ((rect.right - event.clientX) / rect.width) * 100)));
          }
        }}
        onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
      />
      <header className="pbi-canvas-heading">
        <div>
          <span className="pbi-mark" aria-hidden="true" />{' '}
          <strong title={binding.name}>{binding.name}</strong>
        </div>
        <div className="pbi-actions">
          <Button
            size="sm"
            variant="tertiary"
            isIconOnly
            aria-label={expanded ? 'Restore report size' : 'Expand report'}
            onPress={() => setExpanded((value) => !value)}
          >
            {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </Button>
          <Button
            size="sm"
            variant="tertiary"
            isIconOnly
            aria-label="Close report"
            onPress={onClose}
          >
            <X size={17} />
          </Button>
        </div>
      </header>
      <div className="pbi-scope">
        <label>
          Question scope{' '}
          <select
            aria-label="Power BI question scope"
            value={scope}
            onChange={(event) => setScope(event.target.value as typeof scope)}
          >
            <option value="model">Entire model</option>
            <option value="report_view">Page filters &amp; slicers</option>
          </select>
        </label>
        <p>
          {scope === 'model'
            ? 'Questions use the model and the scope you describe.'
            : 'Captured when you send. Chart-specific filters and cross-highlights are excluded.'}
        </p>
      </div>
      {error ? (
        <div role="alert" className="pbi-canvas-message">
          <p>{error}</p>
          <Button variant="secondary" onPress={() => setAttempt((value) => value + 1)}>
            <RefreshCw size={14} />
            Retry report
          </Button>
        </div>
      ) : (
        !ready && (
          <p role="status" className="pbi-canvas-status">
            Opening Power BI report…
          </p>
        )
      )}
      <div ref={host} className="pbi-embed-host" hidden={Boolean(error)} />
    </aside>
  );
}

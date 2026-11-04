import { Button, Dropdown, Label, Modal, Tooltip } from '@heroui/react';
import { useCallback, useId, useRef, useState, type ReactNode } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Info,
  Maximize2,
  Minimize2,
  MoreHorizontal,
  X,
  type LucideIcon,
} from 'lucide-react';

export type ArtifactAction = {
  id: string;
  label: string;
  icon: LucideIcon;
  run(): void | Promise<void>;
  disabled?: boolean;
  busy?: boolean;
  active?: boolean;
};
export type ArtifactMetadata = {
  rowCount?: number;
  artifactId?: string;
  jobId?: string;
  notes?: string[];
  sources?: Array<{
    name: string;
    rowCount?: number | null;
    durationMs?: number | null;
    sql?: string;
    dax?: string;
    executionId?: string;
    truncated?: boolean;
  }>;
};

export function ArtifactIconButton({
  action,
  className = '',
}: {
  action: ArtifactAction;
  className?: string;
}) {
  const Icon = action.icon;
  return (
    <Tooltip delay={350}>
      <Button
        isIconOnly
        size="sm"
        variant="ghost"
        className={`artifact-icon-button ${className}`}
        aria-label={action.label}
        isDisabled={action.disabled}
        aria-disabled={action.disabled || action.busy || undefined}
        aria-busy={action.busy || undefined}
        aria-pressed={action.active}
        onPress={() => {
          if (!action.busy) void action.run();
        }}
      >
        <Icon size={15} aria-hidden="true" />
      </Button>
      <Tooltip.Content className="artifact-tooltip">{action.label}</Tooltip.Content>
    </Tooltip>
  );
}

function ArtifactDetails({
  title,
  metadata,
  open,
  onOpenChange,
}: {
  title: string;
  metadata: ArtifactMetadata;
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  return (
    <Modal.Backdrop isOpen={open} onOpenChange={onOpenChange} className="artifact-details-backdrop">
      <Modal.Container size="full" className="artifact-details-container">
        <Modal.Dialog aria-label={`${title} information`} className="artifact-details-panel">
          <header className="artifact-viewer-header">
            <h3>Result information</h3>
            <ArtifactIconButton
              action={{
                id: 'close-info',
                label: 'Close result information',
                icon: X,
                run: () => onOpenChange(false),
              }}
            />
          </header>
          <div className="artifact-details-body">
            <p className="artifact-details-title">{title}</p>
            {metadata.rowCount != null && (
              <dl>
                <dt>Rows</dt>
                <dd>{metadata.rowCount.toLocaleString()}</dd>
              </dl>
            )}
            {metadata.sources?.map((source, index) => (
              <section className="artifact-source-details" key={source.executionId ?? index}>
                <dl>
                  <dt>Data source</dt>
                  <dd>{source.name}</dd>
                  {source.rowCount != null && (
                    <>
                      <dt>Source rows</dt>
                      <dd>{source.rowCount.toLocaleString()}</dd>
                    </>
                  )}
                  {source.durationMs != null && (
                    <>
                      <dt>Execution time</dt>
                      <dd>{source.durationMs.toLocaleString()} ms</dd>
                    </>
                  )}
                </dl>
                {source.truncated && (
                  <p className="artifact-warning" role="status">
                    The source result is truncated.
                  </p>
                )}
                {source.sql && (
                  <details>
                    <summary>SQL query</summary>
                    <pre aria-label="SQL query">
                      <code>{source.sql}</code>
                    </pre>
                  </details>
                )}
                {source.dax && <details><summary>DAX query</summary><pre aria-label="DAX query"><code>{source.dax}</code></pre></details>}
              </section>
            ))}
            {metadata.notes?.map((note) => (
              <p key={note} className="artifact-details-note">
                {note}
              </p>
            ))}
            {(metadata.artifactId ||
              metadata.jobId ||
              metadata.sources?.some((source) => source.executionId)) && (
              <details>
                <summary>Technical references</summary>
                <dl>
                  {metadata.artifactId && (
                    <>
                      <dt>Artifact</dt>
                      <dd>{metadata.artifactId}</dd>
                    </>
                  )}
                  {metadata.jobId && (
                    <>
                      <dt>Job</dt>
                      <dd>{metadata.jobId}</dd>
                    </>
                  )}
                  {metadata.sources
                    ?.filter((source) => source.executionId)
                    .map((source) => (
                      <div key={source.executionId}>
                        <dt>SQL execution</dt>
                        <dd>{source.executionId}</dd>
                      </div>
                    ))}
                </dl>
              </details>
            )}
          </div>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}

export function ArtifactFrame({
  title,
  kind,
  icon: Icon,
  children,
  actions = [],
  moreActions = [],
  metadata = {},
  defaultOpen = true,
  collapsible = true,
  warning,
  className = '',
  fullscreen: controlledFullscreen,
  onFullscreenChange,
  tools,
}: {
  title: string;
  kind: string;
  icon?: LucideIcon;
  children: ReactNode | ((fullscreen: boolean) => ReactNode);
  actions?: ArtifactAction[];
  moreActions?: ArtifactAction[];
  metadata?: ArtifactMetadata;
  defaultOpen?: boolean;
  collapsible?: boolean;
  warning?: string;
  className?: string;
  fullscreen?: boolean;
  onFullscreenChange?(open: boolean): void;
  tools?: (fullscreen: boolean) => ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [internalFullscreen, setFullscreen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const inlineMenuTrigger = useRef<HTMLButtonElement | null>(null);
  const fullscreenMenuTrigger = useRef<HTMLButtonElement | null>(null);
  const fullscreenMenuReturn = useRef<HTMLButtonElement | null>(null);
  const fullscreen = controlledFullscreen ?? internalFullscreen;
  const attachViewer = useCallback(
    (element: HTMLElement | null) => {
      if (!element && !fullscreen && fullscreenMenuReturn.current) {
        const target = fullscreenMenuReturn.current;
        fullscreenMenuReturn.current = null;
        // Wait for the exiting modal and menu focus scopes to finish cleanup.
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            if (target.isConnected) target.focus({ preventScroll: true });
          }),
        );
      }
    },
    [fullscreen],
  );
  const contentId = useId();
  const kindLabel = kind.charAt(0).toUpperCase() + kind.slice(1);
  function changeFullscreen(open: boolean) {
    if (open) setIsOpen(true);
    if (onFullscreenChange) onFullscreenChange(open);
    else setFullscreen(open);
  }
  const info: ArtifactAction = {
    id: 'information',
    label: `${kindLabel} information`,
    icon: Info,
    run: () => setDetailsOpen(true),
  };
  const expand: ArtifactAction = {
    id: 'fullscreen',
    label: `Expand ${kind} to full screen`,
    icon: Maximize2,
    run: () => changeFullscreen(true),
  };
  const menu = [...actions, ...moreActions, info, ...(fullscreen ? [] : [expand])];
  const content = typeof children === 'function' ? children(fullscreen) : children;
  function header(expanded: boolean) {
    return (
      <header
        ref={expanded ? attachViewer : undefined}
        className="artifact-viewer-header"
        data-collapsible={!expanded && collapsible}
        onClick={(event) => {
          if (expanded || !collapsible) return;
          const target = event.target as Element;
          if (
            target.closest(
              'button, a, input, select, textarea, [role="button"], [role="menu"], [role="menuitem"]',
            )
          )
            return;
          setIsOpen((open) => !open);
        }}
      >
        <div className="artifact-heading">
          {Icon && <Icon size={15} aria-hidden="true" />}
          <h4>
            {!expanded && collapsible ? (
              <button
                type="button"
                className="artifact-header-toggle"
                aria-label={`${isOpen ? 'Hide' : 'View'} ${title}`}
                aria-expanded={isOpen}
                aria-controls={contentId}
                onClick={() => setIsOpen((open) => !open)}
              >
                {title}
              </button>
            ) : (
              title
            )}
          </h4>
          {warning && (
            <span className="artifact-warning" role="status">
              {warning}
            </span>
          )}
        </div>
        <div className="artifact-controls" aria-label={`${title} controls`}>
          <div className="artifact-secondary-actions">
            {actions.map((action) => (
              <ArtifactIconButton action={action} key={action.id} />
            ))}
            {!expanded && <ArtifactIconButton action={expand} />}
          </div>
          <Dropdown>
            <Dropdown.Trigger
              ref={expanded ? fullscreenMenuTrigger : inlineMenuTrigger}
              className="artifact-icon-button"
              aria-label={`${kindLabel} actions`}
            >
              <MoreHorizontal size={16} aria-hidden="true" />
            </Dropdown.Trigger>
            <Dropdown.Popover className="artifact-action-menu">
              <Dropdown.Menu
                aria-label={`${kindLabel} actions`}
                disabledKeys={menu
                  .filter((action) => action.disabled || action.busy)
                  .map((action) => action.id)}
                onAction={(key) => {
                  const action = menu.find((item) => item.id === key);
                  if (action) {
                    // The menu item disappears when its action opens another overlay.
                    // Capture the persistent trigger as the focus return point first.
                    (expanded ? fullscreenMenuTrigger : inlineMenuTrigger).current?.focus();
                    if (key === 'fullscreen')
                      fullscreenMenuReturn.current = inlineMenuTrigger.current;
                    void action.run();
                  }
                }}
              >
                {menu.map((action) => (
                  <Dropdown.Item key={action.id} id={action.id} textValue={action.label}>
                    <action.icon size={14} aria-hidden="true" />
                    <Label>{action.label}</Label>
                  </Dropdown.Item>
                ))}
              </Dropdown.Menu>
            </Dropdown.Popover>
          </Dropdown>
          {expanded ? (
            <ArtifactIconButton
              action={{
                id: 'exit',
                label: `Exit ${kind} full screen`,
                icon: Minimize2,
                run: () => changeFullscreen(false),
              }}
            />
          ) : (
            collapsible && (
              <Button
                isIconOnly
                size="sm"
                variant="ghost"
                className="artifact-icon-button"
                aria-label={`${isOpen ? 'Hide' : 'View'} ${kind}`}
                aria-expanded={isOpen}
                aria-controls={contentId}
                onPress={() => setIsOpen((open) => !open)}
              >
                {isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              </Button>
            )
          )}
        </div>
      </header>
    );
  }
  return (
    <section className={`artifact-frame ${className}`} aria-label={title} data-collapsed={!isOpen}>
      {header(false)}
      {isOpen && !fullscreen && (
        <div className="artifact-frame-content" id={contentId}>
          {tools?.(false)}
          {content}
        </div>
      )}
      <Modal.Backdrop
        isOpen={fullscreen}
        onOpenChange={changeFullscreen}
        className="artifact-fullscreen-backdrop"
      >
        <Modal.Container size="full">
          <Modal.Dialog aria-label={title} className="artifact-fullscreen">
            {header(true)}
            {fullscreen && (
              <div className="artifact-frame-content" id={contentId}>
                {tools?.(true)}
                {content}
              </div>
            )}
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
      <ArtifactDetails
        title={title}
        metadata={metadata}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
      />
    </section>
  );
}

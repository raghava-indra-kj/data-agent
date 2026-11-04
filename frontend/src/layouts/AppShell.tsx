import { Dropdown, Label, Modal, Tooltip } from '@heroui/react';
import { Outlet, useNavigate, useLocation, Link } from 'react-router';
import { useEffect, useId, useRef, useState } from 'react';
import {
  LayoutDashboard,
  Database,
  Settings,
  Building2,
  ChevronDown,
  LogOut,
  SlidersHorizontal,
  Menu,
  Plus,
  X,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  MoreHorizontal,
  Trash2,
} from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { useOrganization } from '../organizations/OrganizationProvider';
import { useConversationList } from '../conversations/hooks/useConversations';
import { ConversationActions } from '../conversations/components/ConversationActions';
import { ConversationListItemContent } from '../conversations/components/ConversationListItemContent';
import { DeleteAllChatsModal } from '../conversations/components/DeleteAllChatsModal';
import { BRANDING } from '../lib/branding';
import { useSidebarDisplay } from './useSidebarDisplay';
import { DisplaySettingsModal } from './DisplaySettingsModal';
import { preferences } from '../lib/preferences';
import { setShowCost, useShowCost } from '../lib/useShowCost';
import { BrandLogo } from '../components/BrandLogo';
import { UserAvatar } from '../components/UserAvatar';
import { LoadMoreSentinel } from '../components/LoadMoreSentinel';

const navigationItems = [
  { label: 'Dashboards', to: '/dashboards', icon: LayoutDashboard },
  { label: 'Data sources', to: '/data-sources', icon: Database },
] as const;
const moreNavigationItems = [
  { label: 'Knowledge', to: '/knowledge' },
  { label: 'Templates', to: '/skills' },
  { label: 'Models', to: '/models' },
  { label: 'Jobs', to: '/jobs' },
] as const;

function ClearChatsButton({ onClick }: { onClick(): void }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipId = useId();
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', dismiss);
    return () => document.removeEventListener('keydown', dismiss);
  }, [open]);
  return (
    <Tooltip isOpen={open} onOpenChange={setOpen}>
      <button
        ref={triggerRef}
        type="button"
        className="sidebar-history-clear-btn"
        aria-label="Delete all chats"
        aria-describedby={open ? tooltipId : undefined}
        onPointerEnter={(event) => {
          if (event.pointerType !== 'touch') setOpen(true);
        }}
        onPointerLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => {
          setOpen(false);
          onClick();
        }}
      >
        <Trash2 size={14} aria-hidden="true" />
      </button>
      <Tooltip.Content triggerRef={triggerRef} placement="right">
        <span id={tooltipId}>Delete all chats</span>
      </Tooltip.Content>
    </Tooltip>
  );
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const { organizations, activeOrganization, setActiveOrganization } = useOrganization();
  const { visibility, isTabVisible, toggleTab, resetDefaults } = useSidebarDisplay();
  const showCost = useShowCost();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [displaySettingsOpen, setDisplaySettingsOpen] = useState(false);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [collapsed, setCollapsed] = useState(() => preferences.get('navigationCollapsed') ?? false);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => setSearchQuery(searchFilter.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchFilter]);
  const conversations = useConversationList(searchQuery);
  const recentList = conversations.conversations;
  const accountName = user?.display_name?.trim() || user?.email || 'Account';
  const visibleMoreItems = moreNavigationItems.filter(({ to }) => isTabVisible(to));
  const moreActive = visibleMoreItems.some(({ to }) => location.pathname.startsWith(to));
  function changeCollapsed(value: boolean) {
    setCollapsed(value);
    preferences.set('navigationCollapsed', value);
  }
  function go(path: string) {
    setMobileOpen(false);
    void navigate(path);
  }
  async function logout() {
    await signOut();
    void navigate('/login', { replace: true });
  }

  function sidebar(mobile = false) {
    const compact = !mobile && collapsed;
    return (
      <>
        <div className="sidebar-brand-row">
          <button
            type="button"
            className="sidebar-brand"
            aria-label="Data Agent home"
            onClick={() => go('/ask')}
          >
            <BrandLogo decorative />
            <span className="sidebar-label">{BRANDING.name}</span>
          </button>
          <button
            type="button"
            className="shell-icon-button sidebar-collapse"
            aria-label={
              mobile ? 'Close navigation' : compact ? 'Expand sidebar' : 'Collapse sidebar'
            }
            title={
              mobile
                ? 'Close navigation'
                : compact
                  ? 'Show navigation and chats'
                  : 'Collapse sidebar'
            }
            aria-expanded={mobile ? true : !collapsed}
            onClick={() => (mobile ? setMobileOpen(false) : changeCollapsed(!collapsed))}
          >
            {mobile ? (
              <X size={18} />
            ) : compact ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
          </button>
        </div>
        <button
          type="button"
          className="sidebar-new"
          aria-label="New chat"
          title={compact ? 'New chat' : undefined}
          onClick={() => go('/ask')}
        >
          <Plus size={18} />
          <span className="sidebar-label">New chat</span>
        </button>
        <div className="sidebar-scroll">
          <nav className="sidebar-navigation" aria-label="Primary navigation">
            {navigationItems
              .filter(({ to }) => isTabVisible(to))
              .map(({ label, to, icon: Icon }) => {
                const active = location.pathname.startsWith(to);
                return (
                  <Link
                    key={to}
                    to={to}
                    aria-label={label}
                    title={compact ? label : undefined}
                    aria-current={active ? 'page' : undefined}
                    className={`sidebar-nav-link ${active ? 'is-active' : ''}`}
                    onClick={() => setMobileOpen(false)}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span className="sidebar-label">{label}</span>
                  </Link>
                );
              })}
            {visibleMoreItems.length > 0 && (
              <Dropdown>
                <Tooltip delay={350}>
                  <Dropdown.Trigger
                    className={`sidebar-nav-link ${moreActive ? 'is-active' : ''}`}
                    aria-label="More navigation"
                  >
                    <MoreHorizontal size={18} aria-hidden="true" />
                    <span className="sidebar-label">More</span>
                  </Dropdown.Trigger>
                  <Tooltip.Content>More tools</Tooltip.Content>
                </Tooltip>
                <Dropdown.Popover className="shell-popover">
                  <Dropdown.Menu aria-label="More tools" onAction={(key) => go(String(key))}>
                    {visibleMoreItems.map(({ label, to }) => (
                      <Dropdown.Item key={to} id={to} textValue={label}>
                        <Label>{label}</Label>
                      </Dropdown.Item>
                    ))}
                  </Dropdown.Menu>
                </Dropdown.Popover>
              </Dropdown>
            )}
          </nav>
          {!compact && (
            <section className="sidebar-history" aria-label="Recent chats">
              <div className="sidebar-history-header">
                <h2>Recent chats</h2>
                {Boolean(recentList.length || searchQuery) && (
                  <ClearChatsButton onClick={() => {
                    if (mobile) setMobileOpen(false);
                    setDeleteAllOpen(true);
                  }} />
                )}
              </div>
              <div className="sidebar-search-field db-icon-search">
                <Search size={14} aria-hidden="true" />
                <input
                  className="db-icon-search__input"
                  aria-label="Search conversation history"
                  placeholder="Search chats…"
                  value={searchFilter}
                  onChange={(event) => setSearchFilter(event.target.value)}
                />
              </div>
              {recentList.map((chat) => (
                <div
                  className={`sidebar-chat-row ${location.pathname === `/conversations/${chat.id}` ? 'is-active' : ''}`}
                  key={chat.id}
                >
                  <Link
                    to={`/conversations/${chat.id}`}
                    onClick={() => setMobileOpen(false)}
                    className="sidebar-chat-link"
                  >
                    <ConversationListItemContent conversation={chat} compact />
                  </Link>
                  <ConversationActions id={chat.id} title={chat.title} compact />
                </div>
              ))}
              {conversations.isLoading && (
                <p className="sidebar-history-state" role="status">
                  Loading chats…
                </p>
              )}
              {recentList.length > 0 && (
                <LoadMoreSentinel
                  className="sidebar-history-state"
                  hasMore={conversations.hasNextPage}
                  isLoading={conversations.isFetchingNextPage}
                  isError={conversations.isFetchNextPageError}
                  onLoadMore={() => void conversations.fetchNextPage()}
                  loadingLabel="Loading more chats…"
                />
              )}
              {conversations.isError && !conversations.isFetchNextPageError && (
                <button
                  className="sidebar-history-state"
                  type="button"
                  onClick={() => void conversations.refetch()}
                >
                  Unable to load chats. Retry
                </button>
              )}
              {!conversations.isLoading && !conversations.isError && !recentList.length && (
                <p className="sidebar-history-state">
                  {searchFilter ? 'No matching chats' : 'No chats yet'}
                </p>
              )}
            </section>
          )}
        </div>
        <footer className="sidebar-footer" aria-label="Workspace and account">
          <Dropdown>
            <Tooltip delay={350}>
              <Dropdown.Trigger
                className="sidebar-footer-control"
                aria-label={`Switch organization: ${activeOrganization?.name ?? 'Workspace'}`}
              >
                <span className="sidebar-workspace-icon">
                  <Building2 size={18} />
                </span>
                <span className="sidebar-footer-text sidebar-label">
                  <span>Workspace</span>
                  <strong>{activeOrganization?.name ?? 'Workspace'}</strong>
                </span>
                <ChevronDown className="sidebar-label" size={14} />
              </Dropdown.Trigger>
              <Tooltip.Content>{activeOrganization?.name ?? 'Switch organization'}</Tooltip.Content>
            </Tooltip>
            <Dropdown.Popover className="shell-popover">
              <Dropdown.Menu
                aria-label="Switch organization"
                selectionMode="single"
                selectedKeys={activeOrganization ? [activeOrganization.id] : []}
                onAction={(key) => {
                  if (String(key) !== activeOrganization?.id) {
                    setActiveOrganization(String(key));
                    go('/ask');
                  }
                }}
              >
                {organizations.map((organization) => (
                  <Dropdown.Item
                    key={organization.id}
                    id={organization.id}
                    textValue={organization.name}
                  >
                    <Label>{organization.name}</Label>
                    <Dropdown.ItemIndicator />
                  </Dropdown.Item>
                ))}
              </Dropdown.Menu>
            </Dropdown.Popover>
          </Dropdown>
          <Dropdown>
            <Tooltip delay={350}>
              <Dropdown.Trigger
                className="sidebar-footer-control"
                aria-label={`User menu: ${accountName}`}
              >
                <UserAvatar name={accountName} />
                <span className="sidebar-footer-text sidebar-label">
                  <strong>{accountName}</strong>
                  <span>Account</span>
                </span>
                <ChevronDown className="sidebar-label" size={14} />
              </Dropdown.Trigger>
              <Tooltip.Content>{accountName}</Tooltip.Content>
            </Tooltip>
            <Dropdown.Popover className="shell-popover">
              <Dropdown.Menu
                aria-label="Account actions"
                onAction={(key) => {
                  if (key === 'settings') go('/settings');
                  if (key === 'display') {
                    setMobileOpen(false);
                    setDisplaySettingsOpen(true);
                  }
                  if (key === 'logout') void logout();
                }}
              >
                <Dropdown.Item id="settings" textValue="Settings">
                  <Settings size={16} />
                  <Label>Settings</Label>
                </Dropdown.Item>
                <Dropdown.Item id="display" textValue="Display settings">
                  <SlidersHorizontal size={16} />
                  <Label>Display settings</Label>
                </Dropdown.Item>
                <Dropdown.Item id="logout" textValue="Sign out">
                  <LogOut size={16} />
                  <Label>Sign out</Label>
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown.Popover>
          </Dropdown>
        </footer>
      </>
    );
  }
  return (
    <div className="app-shell" data-sidebar-collapsed={collapsed ? 'true' : 'false'}>
      <aside className="app-sidebar" aria-label="Application sidebar">
        {sidebar()}
      </aside>
      <button
        type="button"
        className="shell-icon-button mobile-navigation-toggle"
        aria-label="Open navigation"
        onClick={() => setMobileOpen(true)}
      >
        <Menu size={20} />
      </button>
      <main className="main-content">
        <Outlet />
      </main>
      <Modal.Backdrop
        isOpen={mobileOpen}
        onOpenChange={setMobileOpen}
        className="navigation-backdrop"
      >
        <Modal.Container size="full" className="navigation-drawer-container">
          <Modal.Dialog aria-label="Navigation" className="navigation-drawer">
            {sidebar(true)}
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
      <DisplaySettingsModal
        isOpen={displaySettingsOpen}
        onClose={() => setDisplaySettingsOpen(false)}
        visibility={visibility}
        onToggleTab={toggleTab}
        showCost={showCost}
        onToggleShowCost={() => setShowCost(!showCost)}
        onResetDefaults={() => {
          resetDefaults();
          setShowCost(true);
        }}
      />
      <DeleteAllChatsModal
        isOpen={deleteAllOpen}
        onClose={() => setDeleteAllOpen(false)}
      />
    </div>
  );
}

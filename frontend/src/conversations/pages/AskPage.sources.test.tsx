import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { preferences } from '../../lib/preferences';
import { AskPage } from './AskPage';

const state = vi.hoisted(() => ({
  orgId: 'org1',
  userId: 'u1',
  sources: [] as { id: string; name: string; status: string; display_type: string }[],
}));
vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { id: state.userId, email: 'user@example.com' } }),
}));
vi.mock('../../organizations/OrganizationProvider', () => ({
  useOrganization: () => ({ activeOrganization: { id: state.orgId } }),
}));
vi.mock('../../settings/hooks/useInstructions', () => ({ useInstructions: () => ({ data: [] }) }));
vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => ({
    data: queryKey[0] === 'data-sources' ? state.sources : [],
    isLoading: false,
    isError: false,
  }),
  useQueryClient: () => ({ resetQueries: vi.fn() }),
  useInfiniteQuery: () => ({
    data: {
      pages: [
        { items: [{ schema: 'dbo', name: 'orders', object_type: 'table', column_count: 4 }] },
      ],
    },
    isPending: false,
    isError: false,
    hasNextPage: false,
  }),
}));

function showPage() {
  return render(
    <MemoryRouter>
      <AskPage />
    </MemoryRouter>,
  );
}
const warehouse = { id: 'ds1', name: 'Warehouse', status: 'active', display_type: 'postgres' };
const sales = { ...warehouse, id: 'ds2', name: 'Sales' };
const dataScope = () => screen.getByRole('button', { name: 'Data scope' });

describe('Ask source defaults', () => {
  beforeEach(() => {
    state.orgId = 'org1';
    state.userId = 'u1';
    state.sources = [warehouse];
  });

  it('automatically selects the only active source and enables sending', async () => {
    state.sources = [warehouse, { ...sales, status: 'inactive' }];
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/1 data source selected.*Warehouse/);
    await userEvent
      .setup()
      .type(screen.getByRole('textbox', { name: 'Ask a question' }), 'Revenue?');
    expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled();
  });

  it('remembers multiple selections when a new chat is mounted', async () => {
    state.sources = [warehouse, sales];
    showPage();
    const user = userEvent.setup();
    await user.click(dataScope());
    await user.click(screen.getByRole('checkbox', { name: 'Include Warehouse' }));
    await user.click(screen.getByRole('checkbox', { name: 'Include Sales' }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    cleanup();
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/2 data sources selected.*Warehouse, Sales/);
    cleanup();
    state.orgId = 'org2';
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/0 data sources selected/);
    cleanup();
    state.orgId = 'org1';
    state.userId = 'u2';
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/0 data sources selected/);
  });

  it('filters unavailable remembered sources and handles no active sources', () => {
    preferences.set('askDataSourceIdsByScope', {
      [JSON.stringify(['u1', 'org1'])]: ['ds1', 'removed'],
    });
    state.sources = [warehouse, sales];
    const page = showPage();
    expect(dataScope()).toHaveAccessibleDescription(/1 data source selected.*Warehouse/);
    state.sources = [];
    page.rerender(
      <MemoryRouter>
        <AskPage />
      </MemoryRouter>,
    );
    expect(dataScope()).toHaveAccessibleDescription(/0 data sources selected/);
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled();
  });

  it('isolates remembered tables by user and workspace and restores them when a source is reselected', async () => {
    const scope = JSON.stringify(['u1', 'org1']);
    preferences.set('askDataSourceIdsByScope', { [scope]: ['ds1'] });
    preferences.set('askTableSelectionsByScope', {
      [scope]: [
        { data_source_id: 'ds1', mode: 'selected', tables: [{ schema: 'dbo', name: 'orders' }] },
        {
          data_source_id: 'removed',
          mode: 'selected',
          tables: [{ schema: 'dbo', name: 'old_table' }],
        },
      ],
    });
    state.sources = [warehouse, sales];
    showPage();
    const user = userEvent.setup();
    expect(dataScope()).toHaveAccessibleDescription(/Tables: orders/);
    await user.click(dataScope());
    await user.click(screen.getByRole('checkbox', { name: 'Include Warehouse' }));
    await user.click(screen.getByRole('checkbox', { name: 'Include Sales' }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(dataScope()).toHaveAccessibleDescription(/Sales.*Tables: All tables/);
    await user.click(dataScope());
    await user.click(screen.getByRole('checkbox', { name: 'Include Sales' }));
    await user.click(screen.getByRole('checkbox', { name: 'Include Warehouse' }));
    expect(screen.getByRole('checkbox', { name: /orders/ })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(dataScope()).toHaveAccessibleDescription(/Tables: orders/);
    cleanup();
    state.sources = [warehouse];
    state.orgId = 'org2';
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/Tables: All tables/);
    cleanup();
    state.orgId = 'org1';
    state.userId = 'u2';
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/Tables: All tables/);
    cleanup();
    state.userId = 'u1';
    showPage();
    expect(dataScope()).toHaveAccessibleDescription(/Tables: orders/);
  });
});

import { Navigate, createBrowserRouter } from 'react-router';
import { ProtectedRoute } from './route-guards/ProtectedRoute';
import { ErrorBoundary } from '../components/ErrorBoundary';

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/ask" replace /> },
  { path: '/login', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../auth/pages/LoginPage')).LoginPage }) },
  { path: '/signup', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../auth/pages/SignupPage')).SignupPage }) },
  { path: '/forgot-password', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../auth/pages/ForgotPasswordPage')).ForgotPasswordPage }) },
  { path: '/reset-password', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../auth/pages/ResetPasswordPage')).ResetPasswordPage }) },
  {
    element: <ProtectedRoute />,
    errorElement: <ErrorBoundary />,
    children: [
      {
        errorElement: <ErrorBoundary />,
        lazy: async () => ({ Component: (await import('../layouts/AppShell')).AppShell }),
        children: [
          { path: '/power-bi/connected', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../power-bi/PowerBIConnectedPage')).PowerBIConnectedPage }) },
          { path: '/ask', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../conversations/pages/AskPage')).AskPage }) },
          { path: '/conversations/:conversationId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../conversations/pages/ConversationPage')).ConversationPage }) },
          { path: '/dashboards', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../dashboards/pages/DashboardsPage')).DashboardsPage }) },
          { path: '/dashboards/:dashboardId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../dashboards/pages/DashboardDetailPage')).DashboardDetailPage }) },
          { path: '/data-sources', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../data-sources/pages/DataSourcesPage')).DataSourcesPage }) },
          { path: '/data-sources/new', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../data-sources/pages/NewDataSourcePage')).NewDataSourcePage }) },
          { path: '/data-sources/:dataSourceId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../data-sources/pages/DataSourceDetailPage')).DataSourceDetailPage }) },
          { path: '/data-sources/:dataSourceId/edit', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../data-sources/pages/EditDataSourcePage')).EditDataSourcePage }) },
          { path: '/knowledge', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../knowledge/pages/KnowledgePage')).KnowledgePage }) },
          { path: '/skills', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../skills/pages/SkillsPage')).SkillsPage }) },
          { path: '/settings/instructions', element: <Navigate to="/skills" replace /> },
          { path: '/knowledge/:dataSourceId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../knowledge/pages/KnowledgeDetailPage')).KnowledgeDetailPage }) },
          { path: '/models', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../models/pages/ModelsPage')).ModelsPage }) },
          { path: '/models/connections/new', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../models/pages/NewModelConnectionPage')).NewModelConnectionPage }) },
          { path: '/models/connections/:connectionId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../models/pages/ModelConnectionDetailPage')).ModelConnectionDetailPage }) },
          { path: '/models/profiles/new', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../models/pages/NewModelProfilePage')).NewModelProfilePage }) },
          { path: '/models/profiles/:profileId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../models/pages/ModelProfileDetailPage')).ModelProfileDetailPage }) },
          { path: '/jobs', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../jobs/pages/JobsPage')).JobsPage }) },
          { path: '/jobs/:jobId', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../jobs/pages/JobDetailPage')).JobDetailPage }) },
          {
            path: '/settings',
            errorElement: <ErrorBoundary />,
            lazy: async () => ({ Component: (await import('../settings/components/SettingsLayout')).SettingsLayout }),
            children: [
              { index: true, errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../settings/pages/SettingsOverviewPage')).SettingsOverviewPage }) },
              { path: 'organization', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../settings/pages/OrganizationSettingsPage')).OrganizationSettingsPage }) },
              { path: 'audit', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../settings/pages/AuditSettingsPage')).AuditSettingsPage }) },
              { path: 'operations', errorElement: <ErrorBoundary />, lazy: async () => ({ Component: (await import('../settings/pages/OperationsSettingsPage')).OperationsSettingsPage }) },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/ask" replace /> },
]);

import { Button } from '@heroui/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, Link2, LogIn } from 'lucide-react';
import { useLocation } from 'react-router';
import { useAuth } from '../auth/AuthProvider';
import { useOrganization } from '../organizations/OrganizationProvider';
import * as api from './api';
import './power-bi.css';

export function usePowerBIIdentity() {
  const { user } = useAuth();
  const { activeOrganization } = useOrganization();
  return [activeOrganization?.id ?? '', user?.id ?? ''];
}

export function usePowerBIFeatures() {
  const identity = usePowerBIIdentity();
  return useQuery({
    queryKey: ['power-bi', ...identity, 'features'],
    queryFn: api.features,
    retry: false,
    staleTime: 60_000,
  });
}

export function usePowerBIConnection() {
  const identity = usePowerBIIdentity();
  const flags = usePowerBIFeatures();
  const connections = useQuery({
    queryKey: ['power-bi', ...identity, 'connections'],
    queryFn: api.connections,
    enabled: Boolean(flags.data?.enabled && flags.data?.configured),
    retry: false,
  });
  return { flags, connections };
}

export function ConnectionPanel({
  returnTo,
  retry = false,
}: {
  returnTo?: string;
  retry?: boolean;
}) {
  const client = useQueryClient();
  const location = useLocation();
  const { flags, connections } = usePowerBIConnection();
  const connect = useMutation({
    mutationFn: async () => {
      const result = await api.startConnection();
      // Only a local navigation hint is saved. Authentication material stays on the server.
      sessionStorage.setItem('power-bi-return', returnTo ?? location.pathname);
      window.location.assign(result.authorization_url);
    },
  });
  const disconnect = useMutation({
    mutationFn: api.disconnect,
    onSuccess: () => {
      window.dispatchEvent(new Event('power-bi-disconnected'));
      return client.invalidateQueries({ queryKey: ['power-bi'] });
    },
  });
  const connection = connections.data?.[0];
  const error = connect.error || disconnect.error || connections.error || flags.error;
  const loading =
    flags.isPending ||
    (Boolean(flags.data?.enabled && flags.data?.configured) && connections.isPending);
  const connected = connection?.status === 'connected';
  const busy = connect.isPending || disconnect.isPending;
  return (
    <section className="pbi-connection" aria-label="Microsoft connection">
      <div className="pbi-connection-heading">
        <span className="pbi-account-icon">
          <Link2 size={19} aria-hidden="true" />
        </span>
        <div className="pbi-connection-account">
          <strong>Microsoft account</strong>
          <p>
            {loading
              ? 'Checking your connection…'
              : (connection?.display_name ?? 'Connect your account to access Power BI.')}
          </p>
        </div>
        {!loading && (
          <span className="pbi-connection-badge" data-connected={connected}>
            <span aria-hidden="true" />
            {connected ? 'Connected' : connection ? 'Reconnect required' : 'Not connected'}
          </span>
        )}
      </div>
      {flags.data?.enabled && flags.data?.configured ? (
        <div className="pbi-actions">
          <Button
            variant={connected ? 'outline' : 'primary'}
            isPending={connect.isPending}
            isDisabled={busy || loading}
            onPress={() => connect.mutate()}
          >
            <LogIn size={16} aria-hidden="true" />
            {connection ? 'Reconnect Microsoft' : retry ? 'Try again' : 'Connect Microsoft'}
          </Button>
          {connection && (
            <Button
              variant="ghost"
              isPending={disconnect.isPending}
              isDisabled={busy || loading}
              onPress={() => disconnect.mutate(connection.id)}
            >
              Disconnect
            </Button>
          )}
        </div>
      ) : !loading && !flags.error ? (
        <p>Power BI must be enabled and configured by your administrator.</p>
      ) : null}
      {error && (
        <div role="alert" className="pbi-connection-error">
          <CircleAlert size={16} aria-hidden="true" />
          <p>{error.message}</p>
        </div>
      )}
    </section>
  );
}

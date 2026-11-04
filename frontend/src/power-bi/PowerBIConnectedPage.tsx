import { Button, Card } from '@heroui/react';
import {
  ArrowLeft,
  ArrowRight,
  ChartNoAxesCombined,
  CircleAlert,
  CircleCheck,
  ShieldCheck,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { ConnectionPanel } from './ConnectionPanel';
import './power-bi.css';

export function PowerBIConnectedPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const connected = new URLSearchParams(location.search).get('power_bi') === 'connected';
  const saved = sessionStorage.getItem('power-bi-return') ?? '/data-sources/new';
  const destination = /^\/(?:conversations\/[^/]+|data-sources(?:\/[^/]+)?|ask)$/.test(saved)
    ? saved
    : '/data-sources/new';
  const StatusIcon = connected ? CircleCheck : CircleAlert;

  return (
    <section className="pbi-connect-page" aria-labelledby="pbi-connect-title">
      <header className="pbi-connect-page-heading">
        <ChartNoAxesCombined size={19} aria-hidden="true" />
        <span>Power BI connection</span>
      </header>
      <div className="pbi-connect-stage">
        <Card className="pbi-connect-card">
          <Card.Header className="pbi-connect-intro">
            <span className="pbi-connect-status-icon" data-success={connected}>
              <StatusIcon size={27} strokeWidth={1.8} aria-hidden="true" />
            </span>
            <h1 id="pbi-connect-title">
              {connected ? 'Microsoft account connected' : 'Let’s reconnect Microsoft'}
            </h1>
            <p>
              {connected
                ? 'You’re ready to connect your Power BI reports and explore your data.'
                : 'Sign-in wasn’t completed. Try again to connect your Power BI reports.'}
            </p>
          </Card.Header>
          <Card.Content className="pbi-connect-content">
            <ConnectionPanel returnTo={destination} retry={!connected} />
            {!connected && (
              <p className="pbi-connect-help">
                If this keeps happening, ask your administrator to check the Microsoft sign-in
                settings and permissions.
              </p>
            )}
          </Card.Content>
          <Card.Footer className="pbi-connect-footer">
            <Button
              variant={connected ? 'primary' : 'outline'}
              onPress={() => navigate(destination)}
            >
              {!connected && <ArrowLeft size={16} aria-hidden="true" />}
              {connected ? 'Continue to your work' : 'Return to your work'}
              {connected && <ArrowRight size={16} aria-hidden="true" />}
            </Button>
            <p className="pbi-connect-privacy">
              <ShieldCheck size={16} aria-hidden="true" />
              Access follows your Microsoft account’s report permissions.
            </p>
          </Card.Footer>
        </Card>
      </div>
    </section>
  );
}

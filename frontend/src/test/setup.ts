import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { server } from './server';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock);
Element.prototype.getAnimations = () => [];
// Start before application modules capture fetch in their API clients.
server.listen({ onUnhandledRequest: 'error' });
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

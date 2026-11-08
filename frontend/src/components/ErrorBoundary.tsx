import { Component, type ErrorInfo, type ReactNode } from 'react';
import { reportClientError } from '../services/monitoring';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/** Keeps a render error from leaving the customer with a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportClientError(error, 'react-boundary', {
      componentStack: info.componentStack || undefined,
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-void p-6">
          <div className="glass max-w-md space-y-3 p-6 text-center">
            <h1 className="text-xl font-bold">Something went wrong</h1>
            <p className="text-sm text-slate-300">
              Please refresh the page and try again. The technical details have been logged
              securely for the administrator.
            </p>
            <button
              type="button"
              className="btn-primary"
              onClick={() => window.location.reload()}
            >
              Refresh page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
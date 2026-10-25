import React, { Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { StoreProvider } from './store';
import './styles.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="fatal"><h1>Halaman tidak dapat ditampilkan</h1><p>Muat ulang untuk mencoba kembali. Pesanan yang tersimpan tetap aman.</p><button className="button" onClick={() => window.location.reload()}>Muat ulang</button></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ErrorBoundary><StoreProvider><App /></StoreProvider></ErrorBoundary></React.StrictMode>,
);

import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { AlertCircle, ArrowRight, Check, Coffee, LoaderCircle, X } from 'lucide-react';
import { statusLabels, type OrderStatus } from './types';

export function Loading({ label = 'Memuat data…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={24} /><span>{label}</span></div>;
}
export function ErrorBox({ message, retry }: { message?: string; retry?: () => void }) {
  if (!message) return null;
  return <div className="error-box" role="alert"><AlertCircle size={19} /><div><p>{message}</p>{retry && <button className="text-button" onClick={retry}>Coba lagi <ArrowRight size={14} /></button>}</div></div>;
}
export function Empty({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Coffee size={34} /></span><h2>{title}</h2><p>{description}</p>{children}</div>;
}
export function Modal({ title, children, onClose, wide = false, busy = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { dialog?.close(); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, []);
  return <dialog ref={ref} className={`modal ${wide ? 'modal-wide' : ''}`} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={event => { if (!busy && event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    <div className="modal-header"><h2 id={titleId}>{title}</h2><button type="button" className="icon-button" disabled={busy} onClick={onClose} aria-label="Tutup dialog"><X size={21} /></button></div>
    {children}
  </dialog>;
}
export function ProductImage({ src, name, className = '' }: { src: string; name: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const safe = src.startsWith('/') && !src.startsWith('//') || /^https?:\/\//i.test(src);
  return <div className={`product-image ${className}`}>
    {src && safe && !failed ? <img src={src} alt={name} loading="lazy" onError={() => setFailed(true)} /> : <div className="image-fallback" role="img" aria-label={name}><Coffee size={40} /><span>donnih</span></div>}
  </div>;
}
export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status === 'COMPLETED' && <Check size={13} />}{statusLabels[status]}</span>;
}
export function PaymentNotice() {
  return <div className="payment-note"><span className="eyebrow">CASH · PENDING</span><strong>Pembayaran belum diverifikasi; bayar di kasir</strong><p>Demo lokal — tidak ada pembayaran online. Status pesanan bukan bukti pembayaran.</p></div>;
}
export function PageHeading({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description?: string; children?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{children}</div>;
}
export function ConfirmDialog({ title, description, onClose, onConfirm, busy, error, action = 'Arsipkan' }: { title: string; description: string; onClose: () => void; onConfirm: () => void; busy: boolean; error: string; action?: string }) {
  return <Modal title={title} onClose={onClose} busy={busy}><div className="modal-body"><p>{description}</p><ErrorBox message={error} /><div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={onClose}>Batal</button><button className="button" disabled={busy} onClick={onConfirm}>{busy ? 'Menyimpan…' : action}</button></div></div></Modal>;
}

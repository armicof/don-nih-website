import { useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Banknote, Minus, Plus, ShoppingBag, Trash2 } from 'lucide-react';
import { api, money } from './api';
import { navigate, useAction } from './hooks';
import { useStore } from './store';
import { Empty, ErrorBox, Loading, Modal, PageHeading, PaymentNotice, ProductImage } from './ui';
import type { Cart as CartData, Order } from './types';

export function Cart() {
  const store = useStore();
  const { cart } = store;
  const [confirm, setConfirm] = useState(false);
  const mutation = useAction();
  const checkout = useAction();
  const retryKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const busy = mutation.busy || checkout.busy;
  const change = (id: number, quantity?: number) => void mutation.run(async () => {
    const updated = await api<CartData>(`/cart/${id}`, quantity === undefined ? 'DELETE' : 'PATCH', quantity === undefined ? {} : { quantity });
    store.acceptCart(updated);
    retryKey.current = null;
  });
  const placeOrder = () => void checkout.run(async () => {
    if (!store.user) return;
    const storageKey = `donnih-checkout-${store.user.id}`;
    const fingerprint = JSON.stringify(cart.items.map(item => [item.id, item.quantity, item.unit_price, item.toppings.map(topping => topping.id)]));
    if (!retryKey.current || retryKey.current.fingerprint !== fingerprint) {
      let stored: { fingerprint: string; key: string } | null = null;
      try { stored = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); } catch { /* Use a new in-memory key if storage is unavailable. */ }
      retryKey.current = stored?.fingerprint === fingerprint && typeof stored.key === 'string' ? stored : { fingerprint, key: crypto.randomUUID() };
    }
    // Keep the same key after a lost response; never duplicate an accepted order on retry.
    try { sessionStorage.setItem(storageKey, JSON.stringify(retryKey.current)); } catch { /* The ref preserves retries for this mounted page. */ }
    const order = await api<Order>('/orders', 'POST', { idempotency_key: retryKey.current.key });
    retryKey.current = null;
    store.acceptCart({ items: [], total: 0 });
    store.refreshCart();
    setConfirm(false);
    store.notify(`Pesanan #${order.id} berhasil dibuat. Silakan bayar di kasir.`);
    navigate(`/orders/${order.id}`);
  });
  return <>
    <PageHeading eyebrow="ONE STEP CLOSER" title="Keranjang kamu" description="Cek pilihanmu sebelum kami menyiapkannya." />
    <ErrorBox message={store.cartError} retry={store.refreshCart} />
    {store.cartLoading ? <Loading /> : !cart.items.length && !store.cartError ? <Empty title="Keranjang masih kosong" description="Kopi yang enak dimulai dari pilihanmu. Yuk, temukan menu favorit hari ini."><a className="button" href="#/menu">Jelajahi menu <ArrowRight size={18} /></a></Empty> : <div className="cart-layout"><section className="cart-items"><div className="section-top"><h2>Pilihanmu <span className="count-badge">{cart.items.reduce((sum, item) => sum + item.quantity, 0)}</span></h2><a href="#/menu" className="text-button"><Plus size={15} /> Tambah menu</a></div><ErrorBox message={mutation.error} />{cart.items.map(item => <article className={`cart-item ${!item.available ? 'unavailable' : ''}`} key={item.id}><ProductImage src={item.img} name={item.name} /><div className="cart-item-content"><h3>{item.name}</h3><p>{item.toppings.map(topping => topping.name).join(' · ')}</p><span>{money(item.unit_price)} / item</span>{!item.available && <strong className="unavailable-label">Tidak tersedia. Hapus untuk melanjutkan.</strong>}<div className="cart-item-actions"><div className="quantity-control"><button aria-label={`Kurangi jumlah ${item.name}`} disabled={busy || item.quantity <= 1} onClick={() => change(item.id, item.quantity - 1)}><Minus size={15} /></button><output aria-label={`Jumlah ${item.name}`}>{item.quantity}</output><button aria-label={`Tambah jumlah ${item.name}`} disabled={busy || item.quantity >= 99 || !item.available} onClick={() => change(item.id, item.quantity + 1)}><Plus size={15} /></button></div><strong>{money(item.total)}</strong><button className="icon-button danger" disabled={busy} aria-label={`Hapus ${item.name}`} onClick={() => change(item.id)}><Trash2 size={18} /></button></div></div></article>)}</section>
    <aside className="checkout-card"><span className="eyebrow">READY WHEN YOU ARE</span><h2>Ringkasan pesanan</h2><div className="summary-row"><span>Subtotal</span><strong>{money(cart.total)}</strong></div><div className="summary-row"><span>Metode pembayaran</span><span className="cash-label"><Banknote size={18} /> Tunai di kasir</span></div><div className="summary-row total-row"><span>Total</span><strong>{money(cart.total)}</strong></div><PaymentNotice /><button className="button full" disabled={busy || !cart.items.length || !!store.cartError || cart.items.some(item => !item.available)} onClick={() => { checkout.setError(''); setConfirm(true); }}><ShoppingBag size={18} /> Lanjut checkout <ArrowRight size={17} /></button><a className="text-button centered" href="#/menu"><ArrowLeft size={15} /> Kembali belanja</a></aside></div>}
    {confirm && <Modal title="Konfirmasi pesanan" onClose={() => setConfirm(false)} busy={checkout.busy}><div className="modal-body"><p>Pesanan akan dikirim ke barista dan tidak dapat diubah setelah dibuat. Sudah sesuai seleramu?</p><div className="checkout-review">{cart.items.map(item => <div className="summary-row" key={item.id}><span>{item.quantity}× {item.name}</span><strong>{money(item.total)}</strong></div>)}</div><div className="summary-row total-row"><strong>Total pesanan</strong><strong>{money(cart.total)}</strong></div><PaymentNotice /><ErrorBox message={checkout.error} />{checkout.error && <p className="help-text">Belum menerima konfirmasi? Coba lagi dengan tombol di bawah. Kunci pesanan tetap sama untuk mencegah pesanan ganda.</p>}<div className="dialog-actions"><button className="button secondary" disabled={checkout.busy} onClick={() => setConfirm(false)}>Periksa lagi</button><button className="button" disabled={checkout.busy} onClick={placeOrder}>{checkout.busy ? 'Mengirim pesanan…' : checkout.error ? 'Coba kirim lagi' : 'Buat pesanan'}</button></div></div></Modal>}
  </>;
}

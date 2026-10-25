import { useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Clock3, ReceiptText, RefreshCw, Search } from 'lucide-react';
import { api, dateTime, money } from './api';
import { useAction, useQuery } from './hooks';
import { useStore } from './store';
import { nextStatus, statuses, statusLabels, type Order, type OrderStatus } from './types';
import { ConfirmDialog, Empty, ErrorBox, Loading, PageHeading, PaymentNotice, ProductImage, StatusBadge } from './ui';

export function Orders({ admin = false }: { admin?: boolean }) {
  const query = useQuery<Order[]>(admin ? '/admin/orders' : '/orders', 5000);
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');
  const orders = [...(query.data ?? [])].sort((a, b) => b.id - a.id);
  const visible = orders.filter(order => (!filter || order.order_status === filter) && `${order.id} ${order.customer_name}`.toLowerCase().includes(search.toLowerCase()));
  return <>
    <PageHeading eyebrow={admin ? 'DONNIH BACK OFFICE' : 'BREWING GOOD MEMORIES'} title={admin ? 'Kelola pesanan' : 'Pesanan & riwayat'} description={admin ? 'Dari antrean hingga siap dinikmati. Semua dalam satu tempat.' : 'Pantau pesananmu dan temukan kembali rasa favorit.'}><span className="live-label"><span /> Sinkron setiap 5 detik</span></PageHeading>
    {admin && <div className="stats-grid">{statuses.map(status => <button key={status} className={`stat-card ${filter === status ? 'active' : ''}`} onClick={() => setFilter(filter === status ? '' : status)} aria-pressed={filter === status}><span>{statusLabels[status]}</span><strong>{orders.filter(order => order.order_status === status).length}</strong><small>pesanan</small></button>)}</div>}
    <div className="order-toolbar"><div className="category-list"><button className={`pill ${!filter ? 'selected' : ''}`} onClick={() => setFilter('')} aria-pressed={!filter}>Semua</button>{statuses.map(status => <button className={`pill ${filter === status ? 'selected' : ''}`} key={status} onClick={() => setFilter(status)} aria-pressed={filter === status}>{statusLabels[status]}</button>)}</div>{admin && <label className="search-field"><Search size={18} /><input aria-label="Cari nomor pesanan atau pelanggan" placeholder="Nomor pesanan / pelanggan" value={search} onChange={event => setSearch(event.target.value)} /></label>}</div>
    <ErrorBox message={query.error} retry={query.reload} />
    {query.loading ? <Loading /> : !visible.length ? <Empty title={filter || search ? 'Tidak ada pesanan yang cocok' : 'Belum ada cerita di sini'} description={admin ? 'Pesanan pelanggan akan muncul di sini secara otomatis.' : 'Pesanan pertamamu menunggu. Pilih menu, lalu kami siapkan dengan senang hati.'}>{!admin && <a href="#/menu" className="button">Mulai pesan <ArrowRight size={17} /></a>}</Empty> : <div className="orders-list">{visible.map(order => <a className="order-card" key={order.id} href={`#/${admin ? 'admin/' : ''}orders/${order.id}`}><div className="order-card-top"><div className="order-number"><span className="receipt-icon"><ReceiptText size={22} /></span><div><h2>Pesanan #{order.id}</h2><p>{dateTime(order.created_at)}{admin && ` · ${order.customer_name}`}</p></div></div><StatusBadge status={order.order_status} /></div><div className="order-card-bottom"><div className="order-preview">{order.items.slice(0, 3).map((item, index) => <ProductImage key={`${item.id}-${index}`} src={item.img} name={item.name} />)}<span>{order.items.reduce((sum, item) => sum + item.quantity, 0)} item<span className="order-items-label">{order.items.map(item => item.name).join(', ')}</span></span></div><div className="order-card-price"><strong>{money(order.net_income)}</strong><span>Lihat detail <ArrowRight size={16} /></span></div></div><div className="order-payment">Tunai · Pembayaran belum diverifikasi</div></a>)}</div>}
  </>;
}

export function OrderDetail({ id, admin = false }: { id: number; admin?: boolean }) {
  const query = useQuery<Order>(`/orders/${id}`, 5000);
  const { notify } = useStore();
  const action = useAction();
  const [transition, setTransition] = useState<{ from: OrderStatus; to: OrderStatus } | null>(null);
  const order = query.data;
  const next = order ? nextStatus[order.order_status] : undefined;
  const changeStatus = () => void action.run(async () => {
    if (!transition) return;
    try {
      await api<Order>(`/admin/orders/${id}/status`, 'PATCH', { order_status: transition.to, expected_status: transition.from });
      setTransition(null);
      notify('Status pesanan berhasil diperbarui.');
    } finally { query.reload(); }
  });
  return <>
    <a className="back-link" href={`#/${admin ? 'admin/' : ''}orders`}><ArrowLeft size={17} /> Semua pesanan</a>
    <PageHeading eyebrow="ORDER DETAILS" title={`Pesanan #${id}`} description={order ? `${order.customer_name} · ${dateTime(order.created_at)}` : 'Memuat detail pesanan…'}><span className="live-label"><span /> Sinkron setiap 5 detik</span></PageHeading>
    <ErrorBox message={query.error} retry={query.reload} />
    {query.loading ? <Loading /> : order && <div className="order-detail-layout"><div><section className="white-card order-summary"><div className="section-top"><h2>Detail pesanan</h2><StatusBadge status={order.order_status} /></div>{order.items.map((item, index) => <article className="receipt-item" key={`${item.id}-${index}`}><ProductImage src={item.img} name={item.name} /><div><h3>{item.name}</h3><p>{item.toppings.map(topping => `${topping.name}${topping.price ? ` (+${money(topping.price)})` : ''}`).join(' · ')}</p><small>{item.quantity} item</small></div><strong>{money(item.total)}</strong></article>)}<div className="summary-row"><span>Metode pembayaran</span><strong>Tunai (CASH)</strong></div><div className="summary-row total-row"><strong>Total pesanan</strong><strong>{money(order.net_income)}</strong></div><PaymentNotice /></section>{admin && <section className="white-card admin-next"><h2>Aksi pesanan</h2><p>Status hanya dapat dilanjutkan satu tahap. Penyelesaian pesanan tidak memverifikasi pembayaran.</p>{next ? <button className="button" disabled={action.busy || !!query.error} onClick={() => { action.setError(''); setTransition({ from: order.order_status, to: next }); }}>{next === 'CONFIRMED' ? 'Konfirmasi pesanan' : next === 'PROCESSED' ? 'Mulai siapkan pesanan' : 'Tandai pesanan selesai'}<ArrowRight size={18} /></button> : <span className="completed-label"><Check size={18} /> Pesanan selesai — tidak ada aksi berikutnya.</span>}</section>}</div>
    <aside className="white-card timeline-card"><span className="eyebrow">FROM OUR HANDS TO YOURS</span><h2>Perjalanan pesanan</h2><p>Waktu ditampilkan dari riwayat yang tersimpan di server.</p><ol className="timeline">{statuses.map(status => {
      const event = order.events.find(event => event.status === status);
      const current = order.order_status === status;
      return <li key={status} className={`${event ? 'reached' : ''} ${current ? 'current' : ''}`}><span className="timeline-dot">{event ? <Check size={15} /> : <Clock3 size={15} />}</span><div><strong>{statusLabels[status]}</strong><p>{event ? dateTime(event.created_at) : 'Belum ada pembaruan'}</p>{current && <span className="current-label">Status saat ini</span>}</div></li>;
    })}</ol><div className="timeline-footer"><RefreshCw size={14} /><span>Terakhir diperbarui: {dateTime(order.updated_at)}</span></div></aside></div>}
    {transition && <ConfirmDialog title="Perbarui status pesanan?" description={`Pesanan #${id}: ${statusLabels[transition.from]} → ${statusLabels[transition.to]}. Perubahan ini tidak dapat dibatalkan.`} action="Ya, lanjutkan status" busy={action.busy} error={action.error} onClose={() => setTransition(null)} onConfirm={changeStatus} />}
  </>;
}

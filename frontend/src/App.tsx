import { useEffect, useRef, type ReactNode } from 'react';
import { ArrowRight, Coffee, Heart, LayoutGrid, ReceiptText, ShieldCheck, ShoppingBag, SlidersHorizontal, UserRound, X } from 'lucide-react';
import { AdminMenus, AdminToppings } from './Admin';
import { Auth, RequireLogin } from './Auth';
import { Cart } from './Cart';
import { Catalog } from './Catalog';
import { useRoute } from './hooks';
import { OrderDetail, Orders } from './Orders';
import { Profile } from './Profile';
import { useStore } from './store';
import { Empty, ErrorBox, Loading } from './ui';

const customerNav = [
  { path: '/menu', label: 'Menu', icon: Coffee },
  { path: '/favorites', label: 'Favorit', icon: Heart },
  { path: '/cart', label: 'Keranjang', icon: ShoppingBag },
  { path: '/orders', label: 'Pesanan', icon: ReceiptText },
  { path: '/profile', label: 'Profil', icon: UserRound },
];
const adminNav = [
  { path: '/admin/orders', label: 'Pesanan', icon: ReceiptText },
  { path: '/admin/menus', label: 'Kelola menu', icon: LayoutGrid },
  { path: '/admin/toppings', label: 'Topping', icon: SlidersHorizontal },
  { path: '/profile', label: 'Profil', icon: UserRound },
];
export function App() {
  const route = useRoute();
  const store = useStore();
  const mainRef = useRef<HTMLElement>(null);
  const adminMode = route.startsWith('/admin');
  const authRoute = route === '/login' || route === '/register';
  const nav = adminMode && store.user?.role === 'admin' ? adminNav : customerNav;
  const cartCount = store.cart.items.reduce((sum, item) => sum + item.quantity, 0);
  useEffect(() => {
    const label = [...customerNav, ...adminNav].find(item => route === item.path || route.startsWith(`${item.path}/`))?.label || (authRoute ? 'Akun' : 'Donnih');
    document.title = `${label} · Donnih`;
    mainRef.current?.focus({ preventScroll: true });
  }, [route, authRoute]);
  const toast = store.notice && <div className="toast" role="status"><span>{store.notice}</span><button className="icon-button" aria-label="Tutup pemberitahuan" onClick={store.dismissNotice}><X size={17} /></button></div>;
  if (authRoute) return <><Auth key={route} register={route === '/register'} />{toast}</>;
  let page: ReactNode;
  const privateRoute = route !== '/menu' && route !== '/';
  if (store.user === undefined && privateRoute) page = store.authError ? <ErrorBox message={store.authError} retry={store.retryAuth} /> : <Loading label="Memeriksa sesi…" />;
  else if (privateRoute && !store.user) page = <RequireLogin />;
  else if (adminMode && store.user?.role !== 'admin') page = <Empty title="Halaman khusus administrator" description="Akun ini tidak memiliki akses pengelolaan. Silakan kembali ke menu."><a href="#/menu" className="button">Kembali ke menu</a></Empty>;
  else if (/^\/(admin\/)?orders\/\d+$/.test(route)) page = <OrderDetail key={route} id={Number(route.split('/').at(-1))} admin={adminMode} />;
  else switch (route) {
    case '/': case '/menu': page = <Catalog />; break;
    case '/favorites': page = <Catalog key="favorites" favoritesOnly />; break;
    case '/cart': page = <Cart />; break;
    case '/orders': page = <Orders />; break;
    case '/profile': page = <Profile key={store.user?.id} />; break;
    case '/admin/menus': page = <AdminMenus />; break;
    case '/admin/toppings': page = <AdminToppings />; break;
    case '/admin': case '/admin/orders': page = <Orders admin />; break;
    default: page = <Empty title="Halaman tidak ditemukan" description="Kembali ke menu untuk melanjutkan."><a href="#/menu" className="button">Lihat menu</a></Empty>;
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Lewati ke konten</a>
    <aside className="sidebar"><a href="#/menu" className="brand"><Coffee size={31} /><span>donnih<span className="brand-dot">.</span></span></a><p className="brand-caption">COFFEE & GOOD COMPANY</p><div className="sidebar-divider" /><span className="nav-heading">{adminMode ? 'WORKSPACE' : 'YOUR DAILY COMPANION'}</span><nav aria-label="Navigasi utama">{nav.map(item => { const active = route === item.path || route.startsWith(`${item.path}/`); return <a key={item.path} href={`#${item.path}`} className={`nav-link ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}><item.icon size={20} /><span>{item.label}</span>{item.path === '/cart' && cartCount > 0 && <span className="nav-count">{cartCount > 99 ? '99+' : cartCount}</span>}</a>; })}</nav>{store.user?.role === 'admin' && <a className="mode-switch" href={adminMode ? '#/menu' : '#/admin/orders'}><ShieldCheck size={18} />{adminMode ? 'Tampilan pelanggan' : 'Ruang admin'}<ArrowRight size={15} /></a>}<div className="sidebar-bottom"><div className="sidebar-message"><Coffee size={25} /><p>Good days start<br />with good coffee.</p><span>Made with love, always.</span></div><small>Pembayaran tunai di kasir.<br />Bukan layanan pembayaran online.</small></div></aside>
    <div className="main-shell"><header className="topbar"><a href="#/menu" className="mobile-brand">donnih<span>.</span></a><div className="topbar-location"><span className="location-dot" />{adminMode ? 'Admin workspace' : 'Coffee & kitchen'}<span className="topbar-separator">/</span><span>Donnih</span></div><div className="topbar-actions">{store.user ? <a href="#/profile" className="user-chip"><span className="avatar">{store.user.avatar_url ? <img src={store.user.avatar_url} alt="" /> : <UserRound size={18} />}</span><span>{store.user.fullname.split(' ')[0]}</span></a> : <a href="#/login" className="button compact">Masuk <ArrowRight size={15} /></a>}</div></header>
    {store.user?.role === 'admin' && <div className="mobile-mode"><a href={adminMode ? '#/menu' : '#/admin/orders'}><ShieldCheck size={14} />{adminMode ? 'Beralih ke tampilan pelanggan' : 'Buka ruang admin'}<ArrowRight size={14} /></a></div>}
    <main id="main-content" tabIndex={-1} ref={mainRef} className="main-content">{!privateRoute && store.authError && <ErrorBox message={`Sesi belum dapat diperiksa: ${store.authError}`} retry={store.retryAuth} />}{page}</main><footer className="page-footer"><span>donnih. <span>Good coffee, good company.</span></span></footer></div>
    <nav className="bottom-nav" aria-label="Navigasi mobile">{nav.map(item => { const active = route === item.path || route.startsWith(`${item.path}/`); return <a key={item.path} href={`#${item.path}`} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}><span className="mobile-nav-icon"><item.icon size={21} />{item.path === '/cart' && cartCount > 0 && <span className="mobile-cart-count">{cartCount > 99 ? '99+' : cartCount}</span>}</span><span>{item.label}</span></a>; })}</nav>
    {toast}
  </div>;
}

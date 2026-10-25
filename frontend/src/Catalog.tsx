import { useEffect, useState } from 'react';
import { ArrowRight, Check, Coffee, Heart, Plus, Search, ShoppingBag, Sparkles, X } from 'lucide-react';
import { api, money } from './api';
import { navigate, useAction, useQuery } from './hooks';
import { useStore } from './store';
import { categories, categoryLabels, type Cart, type Menu, type Topping } from './types';
import { Empty, ErrorBox, Loading, Modal, PageHeading, ProductImage } from './ui';

function FavoriteButton({ menu }: { menu: Menu }) {
  const store = useStore();
  const { busy, error, run } = useAction();
  const active = store.favorites.includes(menu.id);
  return <div className="favorite-control"><button className={`icon-button favorite-button ${active ? 'is-favorite' : ''}`} disabled={busy || store.favoritesLoading || !!store.favoritesError}
    aria-label={`${active ? 'Hapus' : 'Simpan'} ${menu.name} ${active ? 'dari' : 'ke'} favorit`} aria-pressed={active}
    onClick={() => {
      if (!store.user) { navigate('/login'); return; }
      void run(() => store.toggleFavorite(menu.id));
    }}><Heart size={19} fill={active ? 'currentColor' : 'none'} /></button>{error && <span className="favorite-error" role="alert">{error}</span>}</div>;
}

export function Catalog({ favoritesOnly = false }: { favoritesOnly?: boolean }) {
  const store = useStore();
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [category, setCategory] = useState('');
  const [selected, setSelected] = useState<Menu | null>(null);
  useEffect(() => { const timer = setTimeout(() => setDebounced(search), 250); return () => clearTimeout(timer); }, [search]);
  const query = useQuery<Menu[]>(`/menus?search=${encodeURIComponent(debounced)}&category=${encodeURIComponent(category)}`);
  const menus = (query.data ?? []).filter(menu => menu.active && (!favoritesOnly || store.favorites.includes(menu.id)));
  return <>
    <PageHeading eyebrow={favoritesOnly ? 'MADE FOR YOU' : 'A LITTLE COFFEE, A LOT OF JOY'} title={favoritesOnly ? 'Favorit kamu' : `Welcome, ${store.user?.fullname.split(' ')[0] || 'Guest'}!`} description={favoritesOnly ? 'Pilihan yang selalu bikin ingin kembali.' : 'Mau ditemani rasa apa hari ini?'} />
    {!favoritesOnly && <section className="coffee-banner"><div><span className="banner-label"><Sparkles size={14} /> BREWED WITH LOVE</span><h2>Temukan rasa.<br />Nikmati momennya.</h2><p>Dari kopi pertama hingga gigitan terakhir.<br />Dibuat untuk menemani harimu.</p><button className="banner-link" onClick={() => document.getElementById('menu-search')?.focus()}>Pilih menu favoritmu <ArrowRight size={17} /></button></div><div className="banner-art"><span className="coffee-ring" /><img src="/images/caffelatte.png" alt="Caffè latte Donnih" onError={event => { event.currentTarget.style.visibility = 'hidden'; }} /><span className="coffee-stamp">freshly<br /><strong>brewed</strong><Coffee size={18} /></span></div></section>}
    <div className="catalog-toolbar"><div><h2>{favoritesOnly ? 'Your favourites' : 'Menu pilihan'}</h2><p>{query.loading ? 'Menyiapkan menu…' : `${menus.length} menu untuk dinikmati`}</p></div><label className="search-field"><Search size={19} /><input id="menu-search" maxLength={100} value={search} onChange={event => setSearch(event.target.value)} placeholder="Cari kopi, makanan, dan lainnya…" aria-label="Cari menu" />{search && <button className="icon-button small" onClick={() => setSearch('')} aria-label="Hapus pencarian"><X size={16} /></button>}</label></div>
    <div className="category-list" aria-label="Kategori menu"><button className={`pill ${category === '' ? 'selected' : ''}`} onClick={() => setCategory('')} aria-pressed={category === ''}>Semua menu</button>{categories.map(value => <button key={value} className={`pill ${category === value ? 'selected' : ''}`} onClick={() => setCategory(value)} aria-pressed={category === value}>{categoryLabels[value]}</button>)}</div>
    <ErrorBox message={store.favoritesError} retry={store.refreshFavorites} />
    <ErrorBox message={query.error} retry={query.reload} />
    {query.loading || (favoritesOnly && store.favoritesLoading) ? <div className="product-grid" aria-label="Memuat menu" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div className="product-card skeleton" key={i}><div /><span /><span /></div>)}</div> : !query.error && menus.length === 0 ? <Empty title={favoritesOnly && !search && !category ? 'Belum ada menu favorit' : 'Menu tidak ditemukan'} description={favoritesOnly ? 'Simpan menu dengan tombol hati, atau coba kategori lain.' : 'Coba kata kunci atau kategori lain untuk menemukan pilihanmu.'}><button className="button secondary" onClick={() => { setSearch(''); setCategory(''); if (favoritesOnly) navigate('/menu'); }}>Lihat semua menu</button></Empty> : <div className="product-grid">{menus.map(menu => <article className="product-card" key={menu.id}><div className="product-visual"><button className="image-button" onClick={() => setSelected(menu)} aria-label={`Lihat detail ${menu.name}`}><ProductImage src={menu.img} name={menu.name} /></button><FavoriteButton menu={menu} /></div><div className="product-info"><span className="eyebrow">{categoryLabels[menu.category]}</span><h3><button onClick={() => setSelected(menu)}>{menu.name}</button></h3><p>{menu.description}</p><div className="product-bottom"><strong>{money(menu.price)}</strong><button className="add-button" aria-label={`Pilih ${menu.name}`} onClick={() => setSelected(menu)}><Plus size={21} /></button></div></div></article>)}</div>}
    {selected && <MenuDetail menu={selected} onClose={() => setSelected(null)} />}
  </>;
}

function MenuDetail({ menu, onClose }: { menu: Menu; onClose: () => void }) {
  const store = useStore();
  const query = useQuery<Topping[]>('/toppings');
  const [size, setSize] = useState(11);
  const [temperature, setTemperature] = useState(10);
  const [extras, setExtras] = useState<number[]>([]);
  const { busy, error, run } = useAction();
  const toppings = query.data?.filter(topping => topping.active) ?? [];
  const selectedIds = [size, temperature, ...extras];
  const price = menu.price + toppings.filter(topping => selectedIds.includes(topping.id)).reduce((sum, topping) => sum + topping.price, 0);
  const valid = toppings.some(topping => topping.id === size && topping.kind === 'size') && toppings.some(topping => topping.id === temperature && topping.kind === 'temperature');
  const add = () => {
    if (!store.user) { onClose(); navigate('/login'); return; }
    void run(async () => {
      const cart = await api<Cart>('/cart', 'POST', { menu_id: menu.id, topping_ids: selectedIds, quantity: 1 });
      store.acceptCart(cart);
      store.notify(`${menu.name} ditambahkan ke keranjang.`);
      onClose();
    });
  };
  return <Modal title="Racik pilihanmu" onClose={onClose} busy={busy} wide><div className="detail-layout"><div className="detail-visual"><ProductImage src={menu.img} name={menu.name} /><span className="detail-category">{categoryLabels[menu.category]} · DONNIH</span></div><div className="detail-content"><span className="eyebrow">A CUP OF HAPPINESS</span><h2>{menu.name}</h2><p>{menu.description}</p><strong className="detail-price">{money(menu.price)} <small>harga dasar</small></strong>
    <ErrorBox message={query.error} retry={query.reload} />{query.loading ? <Loading label="Memuat pilihan rasa…" /> : <fieldset disabled={busy} className="customization">
      {(['size', 'temperature'] as const).map(kind => <fieldset key={kind}><legend>{kind === 'size' ? 'Ukuran' : 'Suhu'} <span>Wajib pilih satu</span></legend><div className="option-grid">{toppings.filter(topping => topping.kind === kind).map(topping => { const checked = (kind === 'size' ? size : temperature) === topping.id; return <label className={`option ${checked ? 'chosen' : ''}`} key={topping.id}><input type="radio" name={kind} value={topping.id} checked={checked} onChange={() => kind === 'size' ? setSize(topping.id) : setTemperature(topping.id)} /><span>{topping.name}<small>{topping.price ? `+ ${money(topping.price)}` : 'Tanpa biaya tambahan'}</small></span>{checked && <Check size={17} />}</label>; })}</div></fieldset>)}
      <fieldset><legend>Extra toppings <span>Opsional</span></legend><div className="topping-list">{toppings.filter(topping => topping.kind === 'extra').map(topping => <label className="topping-option" key={topping.id}><input type="checkbox" checked={extras.includes(topping.id)} onChange={event => setExtras(previous => event.target.checked ? [...previous, topping.id] : previous.filter(id => id !== topping.id))} /><span>{topping.name}</span><strong>+ {money(topping.price)}</strong></label>)}{!toppings.some(topping => topping.kind === 'extra') && <p className="muted">Tidak ada tambahan tersedia.</p>}</div></fieldset>
    </fieldset>}
    {!query.loading && !query.error && !valid && <ErrorBox message="Pilihan ukuran atau suhu belum tersedia. Silakan hubungi kasir." />}
    <ErrorBox message={error} /><div className="detail-total"><div><small>Total per item</small><strong>{money(price)}</strong></div><button className="button" disabled={busy || query.loading || !!query.error || !valid || store.cartLoading} onClick={add}><ShoppingBag size={18} />{busy ? 'Menambahkan…' : store.user ? 'Tambah ke keranjang' : 'Masuk untuk memesan'}</button></div>
  </div></div></Modal>;
}

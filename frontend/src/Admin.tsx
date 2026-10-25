import { useState, type FormEvent } from 'react';
import { Archive, ImagePlus, Pencil, Plus, RotateCcw, Search, SlidersHorizontal } from 'lucide-react';
import { api, money, uploadImage } from './api';
import { useAction, useQuery } from './hooks';
import { useStore } from './store';
import { categories, categoryLabels, type Category, type Menu, type Topping } from './types';
import { ConfirmDialog, Empty, ErrorBox, Loading, Modal, PageHeading, ProductImage } from './ui';

export function AdminMenus() {
  const query = useQuery<Menu[]>('/admin/menus');
  const { notify, refreshCart } = useStore();
  const action = useAction();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [visibility, setVisibility] = useState('all');
  const [editing, setEditing] = useState<Menu | 'new' | null>(null);
  const [archiving, setArchiving] = useState<Menu | null>(null);
  const menus = (query.data ?? []).filter(menu => menu.name.toLowerCase().includes(search.toLowerCase()) && (!category || menu.category === category) && (visibility === 'all' || menu.active === (visibility === 'active')));
  const refresh = () => { query.reload(); refreshCart(); };
  return <>
    <PageHeading eyebrow="DONNIH BACK OFFICE" title="Kelola menu" description="Pilihan yang enak dimulai dari menu yang terawat."><button className="button" onClick={() => setEditing('new')}><Plus size={18} /> Tambah menu</button></PageHeading>
    <div className="white-card admin-toolbar"><label className="search-field"><Search size={19} /><input aria-label="Cari menu admin" value={search} onChange={event => setSearch(event.target.value)} placeholder="Cari nama menu…" /></label><label className="filter-label">Kategori<select value={category} onChange={event => setCategory(event.target.value)}><option value="">Semua kategori</option>{categories.map(value => <option key={value} value={value}>{categoryLabels[value]}</option>)}</select></label><label className="filter-label">Status<select value={visibility} onChange={event => setVisibility(event.target.value)}><option value="all">Semua status</option><option value="active">Aktif</option><option value="archived">Diarsipkan</option></select></label></div>
    <ErrorBox message={query.error} retry={query.reload} /><ErrorBox message={action.error} />
    {query.loading ? <Loading /> : menus.length === 0 ? <Empty title="Belum ada menu yang cocok" description="Tambahkan menu baru atau ubah pencarian dan filter." /> : <div className="admin-menu-grid">{menus.map(menu => <article className={`white-card admin-menu-card ${!menu.active ? 'archived' : ''}`} key={menu.id}><ProductImage src={menu.img} name={menu.name} /><div className="admin-menu-info"><div className="section-top"><span className="eyebrow">{categoryLabels[menu.category]}</span><span className={`availability ${menu.active ? 'active' : ''}`}>{menu.active ? 'Aktif' : 'Diarsipkan'}</span></div><h2>{menu.name}</h2><p>{menu.description}</p><strong>{money(menu.price)}</strong><div className="admin-card-actions"><button className="button secondary compact" onClick={() => setEditing(menu)}><Pencil size={15} /> Edit</button>{menu.active ? <button className="icon-button danger" aria-label={`Arsipkan ${menu.name}`} onClick={() => { action.setError(''); setArchiving(menu); }}><Archive size={18} /></button> : <button className="button secondary compact" disabled={action.busy} onClick={() => void action.run(async () => { await api(`/admin/menus/${menu.id}`, 'PATCH', { active: true }); refresh(); notify('Menu berhasil diaktifkan kembali.'); })}><RotateCcw size={15} /> Aktifkan</button>}</div></div></article>)}</div>}
    <p className="help-text admin-footnote">Menu yang diarsipkan tidak muncul di katalog pelanggan. Riwayat pesanan tetap tersimpan.</p>
    {editing && <MenuEditor menu={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); notify('Menu berhasil disimpan.'); }} />}
    {archiving && <ConfirmDialog title="Arsipkan menu?" description={`“${archiving.name}” tidak lagi dapat dipesan. Anda dapat mengaktifkannya kembali; riwayat tidak dihapus.`} busy={action.busy} error={action.error} onClose={() => setArchiving(null)} onConfirm={() => void action.run(async () => { await api(`/admin/menus/${archiving.id}`, 'DELETE', {}); setArchiving(null); refresh(); notify('Menu berhasil diarsipkan.'); })} />}
  </>;
}

const originalImages = [
  ['caffelatte.png', 'Caffè latte'], ['americano.png', 'Americano'], ['espresso.png', 'Espresso'],
  ['menu_cappucino.png', 'Cappuccino'], ['appletea.png', 'Apple tea'], ['peachtea.png', 'Peach tea'],
  ['pancake.png', 'Pancake'], ['curry.png', 'Curry'],
];
function MenuEditor({ menu, onClose, onSaved }: { menu?: Menu; onClose: () => void; onSaved: () => void }) {
  const save = useAction();
  const upload = useAction();
  const [image, setImage] = useState(menu?.img ?? '');
  const busy = save.busy || upload.busy;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void save.run(async () => {
      if (!image || !(image.startsWith('/') && !image.startsWith('//') || /^https?:\/\//i.test(image))) throw new Error('Pilih aset atau unggah gambar menu terlebih dahulu.');
      const payload = { name: String(form.get('name')).trim(), description: String(form.get('description')).trim(), price: Number(form.get('price')), category: String(form.get('category')) as Category, img: image };
      await api(menu ? `/admin/menus/${menu.id}` : '/admin/menus', menu ? 'PATCH' : 'POST', payload);
      onSaved();
    });
  };
  return <Modal title={menu ? `Edit ${menu.name}` : 'Tambah menu baru'} onClose={onClose} busy={busy} wide><form className="modal-body form" onSubmit={submit}><fieldset disabled={busy}><div className="menu-editor-layout"><div className="menu-image-editor"><ProductImage src={image} name="Pratinjau gambar menu" /><label className="button secondary upload-button"><ImagePlus size={17} />{upload.busy ? 'Mengunggah…' : 'Unggah gambar'}<input type="file" accept="image/png,image/jpeg,image/webp" aria-label="Unggah gambar menu" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload.run(async () => { const result = await uploadImage(file, 'menu'); setImage(result.url); }); }} /></label><small>PNG, JPEG, atau WebP · Maks. 2 MB</small><label>Atau gunakan aset Donnih<select value={originalImages.some(([file]) => image === `/images/${file}`) ? image : ''} onChange={event => { if (event.target.value) setImage(event.target.value); }}><option value="">Pilih gambar asli</option>{originalImages.map(([file, label]) => <option key={file} value={`/images/${file}`}>{label}</option>)}</select></label><ErrorBox message={upload.error} /></div><div className="menu-editor-fields"><label>Nama menu<input name="name" defaultValue={menu?.name} required minLength={2} maxLength={100} placeholder="Contoh: Caffè Latte" /></label><label>Deskripsi<textarea name="description" defaultValue={menu?.description} maxLength={1000} rows={4} placeholder="Ceritakan rasa dan bahan utama menu ini" /></label><label>Harga dasar (Rp)<input name="price" type="number" min={0} max={100000000} step={1} defaultValue={menu?.price} required placeholder="25000" /></label><label>Kategori<select name="category" defaultValue={menu?.category ?? 'COFFEE'}>{categories.map(value => <option key={value} value={value}>{categoryLabels[value]}</option>)}</select></label></div></div></fieldset><ErrorBox message={save.error} /><div className="dialog-actions"><button className="button secondary" type="button" disabled={busy} onClick={onClose}>Batal</button><button className="button" disabled={busy}>{save.busy ? 'Menyimpan…' : 'Simpan menu'}</button></div></form></Modal>;
}

export function AdminToppings() {
  const query = useQuery<Topping[]>('/admin/toppings');
  const { notify, refreshCart } = useStore();
  const action = useAction();
  const [editing, setEditing] = useState<Topping | 'new' | null>(null);
  const [archiving, setArchiving] = useState<Topping | null>(null);
  const refresh = () => { query.reload(); refreshCart(); };
  return <>
    <PageHeading eyebrow="THE LITTLE EXTRAS" title="Topping & pilihan" description="Kelola tambahan rasa, ukuran, dan suhu dari satu tempat."><button className="button" onClick={() => setEditing('new')}><Plus size={18} /> Tambah topping</button></PageHeading>
    <ErrorBox message={query.error} retry={query.reload} /><ErrorBox message={action.error} />
    {query.loading ? <Loading /> : <div className="topping-sections">{(['size', 'temperature', 'extra'] as const).map(kind => <section className="white-card topping-section" key={kind}><div className="section-top"><div><h2>{kind === 'size' ? 'Ukuran' : kind === 'temperature' ? 'Suhu' : 'Extra toppings'}</h2><p>{kind === 'extra' ? 'Tambahan opsional untuk racikan pelanggan.' : 'Pilihan wajib. Nama dan status tetap; harga dapat diubah.'}</p></div><SlidersHorizontal size={21} /></div><div className="admin-topping-list">{(query.data ?? []).filter(topping => topping.kind === kind).map(topping => <article className="admin-topping-row" key={topping.id}><div><h3>{topping.name}</h3><span className={`availability ${topping.active ? 'active' : ''}`}>{topping.active ? 'Aktif' : 'Diarsipkan'}</span></div><strong>{money(topping.price)}</strong><div className="row-actions"><button className="icon-button" aria-label={`Edit ${topping.name}`} onClick={() => setEditing(topping)}><Pencil size={17} /></button>{kind === 'extra' && (topping.active ? <button className="icon-button danger" aria-label={`Arsipkan topping ${topping.name}`} onClick={() => { action.setError(''); setArchiving(topping); }}><Archive size={17} /></button> : <button className="icon-button" disabled={action.busy} aria-label={`Aktifkan topping ${topping.name}`} onClick={() => void action.run(async () => { await api(`/admin/toppings/${topping.id}`, 'PATCH', { active: true }); refresh(); notify('Topping berhasil diaktifkan.'); })}><RotateCcw size={17} /></button>)}</div></article>)}{!(query.data ?? []).some(topping => topping.kind === kind) && <p className="muted">Belum ada pilihan di kategori ini.</p>}</div></section>)}</div>}
    {editing && <ToppingEditor topping={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); notify('Pilihan berhasil disimpan.'); }} />}
    {archiving && <ConfirmDialog title="Arsipkan topping?" description={`“${archiving.name}” tidak lagi tersedia untuk pesanan baru. Riwayat pesanan tetap tersimpan.`} busy={action.busy} error={action.error} onClose={() => setArchiving(null)} onConfirm={() => void action.run(async () => { await api(`/admin/toppings/${archiving.id}`, 'DELETE', {}); setArchiving(null); refresh(); notify('Topping berhasil diarsipkan.'); })} />}
  </>;
}
function ToppingEditor({ topping, onClose, onSaved }: { topping?: Topping; onClose: () => void; onSaved: () => void }) {
  const { busy, error, run } = useAction();
  const fixed = topping && topping.kind !== 'extra';
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(async () => {
      const payload = { price: Number(form.get('price')), ...(!fixed ? { name: String(form.get('name')).trim() } : {}) };
      await api(topping ? `/admin/toppings/${topping.id}` : '/admin/toppings', topping ? 'PATCH' : 'POST', payload);
      onSaved();
    });
  };
  return <Modal title={topping ? `Edit ${topping.name}` : 'Tambah extra topping'} onClose={onClose} busy={busy}><form className="modal-body form" onSubmit={submit}><fieldset disabled={busy}><label>Nama pilihan<input name="name" defaultValue={topping?.name} readOnly={!!fixed} required minLength={2} maxLength={100} /></label><label>Harga tambahan (Rp)<input name="price" type="number" min={0} max={100000000} step={1} defaultValue={topping?.price} required /></label>{fixed && <p className="help-text">Ukuran dan suhu adalah pilihan wajib pada setiap menu. Hanya harga yang dapat diubah.</p>}</fieldset><ErrorBox message={error} /><div className="dialog-actions"><button className="button secondary" type="button" disabled={busy} onClick={onClose}>Batal</button><button className="button" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan pilihan'}</button></div></form></Modal>;
}

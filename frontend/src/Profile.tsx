import { useState, type FormEvent } from 'react';
import { Camera, LogOut, Mail, ShieldCheck, UserRound } from 'lucide-react';
import { api, uploadImage } from './api';
import { navigate, useAction } from './hooks';
import { useStore } from './store';
import type { User } from './types';
import { ConfirmDialog, ErrorBox, PageHeading } from './ui';

export function Profile() {
  const { user, setUser, notify } = useStore();
  const save = useAction();
  const upload = useAction();
  const logout = useAction();
  const [confirmLogout, setConfirmLogout] = useState(false);
  if (!user) return null;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void save.run(async () => {
      const result = await api<{ user: User }>('/profile', 'PATCH', { fullname: String(form.get('fullname')).trim(), phone_number: String(form.get('phone_number')).trim() });
      setUser(result.user);
      notify('Profil berhasil diperbarui.');
    });
  };
  return <>
    <PageHeading eyebrow="A LITTLE MORE ABOUT YOU" title="Profil saya" description="Biar kami mengenalmu sedikit lebih baik." />
    <div className="profile-layout"><aside className="white-card profile-card"><div className="avatar large">{user.avatar_url ? <img src={user.avatar_url} alt={`Foto profil ${user.fullname}`} /> : <UserRound size={48} />}</div><h2>{user.fullname}</h2><p>@{user.username}</p><span className="role-badge"><ShieldCheck size={15} />{user.role === 'admin' ? 'Administrator' : 'Donnih member'}</span><label className={`button secondary upload-button ${upload.busy ? 'disabled' : ''}`}><Camera size={18} />{upload.busy ? 'Mengunggah…' : 'Ganti foto'}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={upload.busy || save.busy} aria-label="Unggah foto profil" onChange={event => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;
      void upload.run(async () => {
        await uploadImage(file, 'avatar');
        const response = await api<{ user: User }>('/auth/me');
        setUser(response.user);
        notify('Foto profil berhasil diperbarui.');
      });
    }} /></label><small>PNG, JPEG, atau WebP · Maks. 2 MB</small><ErrorBox message={upload.error} /></aside>
    <section className="white-card profile-form"><h2>Informasi pribadi</h2><p>Perbarui nama dan nomor yang bisa dihubungi.</p><form className="form" onSubmit={submit}><fieldset disabled={save.busy || upload.busy}><label>Nama lengkap<input name="fullname" defaultValue={user.fullname} autoComplete="name" required minLength={2} maxLength={100} /></label><label>Nomor telepon<input name="phone_number" defaultValue={user.phone_number} type="tel" autoComplete="tel" minLength={6} maxLength={25} pattern="[+0-9 \(\)\-]{6,25}" title="Opsional: 6–25 karakter, gunakan angka, spasi, +, tanda kurung, atau tanda hubung" /></label><label>Email<span className="readonly-field"><Mail size={17} />{user.email}</span></label><label>Username<input value={user.username} readOnly /></label></fieldset><p className="help-text">Email, username, dan peran akun tidak dapat diubah di halaman ini.</p><ErrorBox message={save.error} /><button className="button" disabled={save.busy || upload.busy}>{save.busy ? 'Menyimpan…' : 'Simpan perubahan'}</button></form></section></div>
    <section className="white-card logout-card"><div><h2>Sampai jumpa di cangkir berikutnya</h2><p>Keluar dari akun di perangkat ini.</p></div><button className="button secondary" onClick={() => setConfirmLogout(true)}><LogOut size={17} /> Keluar</button></section>
    {confirmLogout && <ConfirmDialog title="Keluar dari akun?" description="Favorit, keranjang, dan riwayat pesananmu tetap tersimpan di akun." action="Keluar" busy={logout.busy} error={logout.error} onClose={() => setConfirmLogout(false)} onConfirm={() => void logout.run(async () => { await api('/auth/logout', 'POST', {}); setUser(null); notify('Berhasil keluar. Sampai jumpa kembali!'); navigate('/menu'); })} />}
  </>;
}

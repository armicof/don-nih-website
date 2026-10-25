import { useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Coffee, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { api } from './api';
import { navigate, useAction } from './hooks';
import { useStore } from './store';
import { ErrorBox } from './ui';
import type { User } from './types';

export function Auth({ register = false }: { register?: boolean }) {
  const { setUser, notify } = useStore();
  const { busy, error, run } = useAction();
  const [visible, setVisible] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void run(async () => {
      const payload = { email: String(values.get('email')).trim(), password: String(values.get('password')),
        ...(register ? { fullname: String(values.get('fullname')).trim(), username: String(values.get('username')).trim(), phone_number: String(values.get('phone_number')).trim() } : {}),
      };
      const { user } = await api<{ user: User }>(`/auth/${register ? 'register' : 'login'}`, 'POST', payload);
      setUser(user);
      notify(register ? 'Akun berhasil dibuat. Selamat datang di Donnih!' : `Selamat datang kembali, ${user.fullname}!`);
      let destination = user.role === 'admin' ? '/admin/orders' : '/menu';
      try {
        const returnTo = sessionStorage.getItem('donnih-return');
        if (returnTo && /^\/(menu|favorites|cart|orders(?:\/\d+)?|profile)$/.test(returnTo)) destination = returnTo;
        sessionStorage.removeItem('donnih-return');
      } catch { /* Navigation still works without storage. */ }
      navigate(destination);
    });
  };
  return <div className="auth-page">
    <aside className="auth-story"><a href="#/menu" className="brand"><Coffee size={35} /><span>donnih<span className="brand-dot">.</span></span></a><div><span className="eyebrow">YOUR DAILY LITTLE JOY</span><h1>Kopi yang pas.<br />Hari yang lebih<br /><em>hangat.</em></h1><p>Racik pilihanmu, temukan favorit baru,<br />dan nikmati momen kecil bersama Donnih.</p></div><span className="demo-badge"><ShieldCheck size={15} /> Demo lokal · Bayar di kasir</span></aside>
    <section className="auth-main">
      <svg className="auth-wave top" viewBox="0 0 402 134" preserveAspectRatio="none" aria-hidden="true"><path d="M402 0L402 129C370.5 137 333.5 137.5 293.5 100C255.123 64.021 188.5 80.5 146.5 87C104.5 93.5 27 90 0 28V0H402Z" /></svg>
      <a href="#/menu" className="back-link"><ArrowLeft size={17} /> Kembali ke menu</a>
      <div className="auth-form-wrap"><span className="eyebrow">DONNIH COFFEE & KITCHEN</span><h1>{register ? 'Let’s get started!' : 'Welcome Back!'}</h1><p>{register ? 'Buat akun untuk menyimpan favorit dan mulai memesan.' : 'Masuk dan lanjutkan cerita kopimu hari ini.'}</p>
        <form className="form" onSubmit={submit}>
          <fieldset disabled={busy}>
            {register && <><label>Nama lengkap<input name="fullname" autoComplete="name" required minLength={2} maxLength={100} placeholder="Nama lengkap Anda" /></label><label>Username<input name="username" autoComplete="username" required minLength={3} maxLength={30} pattern="[A-Za-z0-9_.\-]+" title="3–30 karakter: huruf, angka, titik, garis bawah, atau tanda hubung" placeholder="Nama pengguna" /></label><label>Nomor telepon<input name="phone_number" type="tel" autoComplete="tel" minLength={6} maxLength={25} pattern="[+0-9 \(\)\-]{6,25}" title="Opsional: 6–25 karakter, gunakan angka, spasi, +, tanda kurung, atau tanda hubung" placeholder="08xxxxxxxxxx" /></label></>}
            <label>Email<input name="email" type="email" autoComplete="email" required maxLength={254} placeholder="nama@email.com" /></label>
            <label>Password<span className="password-field"><input name="password" type={visible ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} required minLength={8} maxLength={128} placeholder={register ? 'Minimal 8 karakter' : 'Masukkan password'} /><button type="button" className="icon-button" onClick={() => setVisible(!visible)} aria-label={visible ? 'Sembunyikan password' : 'Tampilkan password'}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></span></label>
          </fieldset>
          <ErrorBox message={error} />
          <button className="button full" disabled={busy}>{busy ? 'Mohon tunggu…' : register ? 'Buat akun' : 'Masuk'}{!busy && <ArrowRight size={18} />}</button>
        </form>
        <p className="auth-switch">{register ? 'Sudah punya akun?' : 'Belum punya akun?'} <a href={register ? '#/login' : '#/register'}>{register ? 'Masuk' : 'Daftar sekarang'}</a></p>
        <p className="auth-disclaimer"><ShieldCheck size={16} /> Demo lokal. Tidak ada pembayaran online.</p>
      </div>
      <svg className="auth-wave bottom" viewBox="0 0 402 134" preserveAspectRatio="none" aria-hidden="true"><path d="M0 133.377L0 4.37683C31.5 -3.62317 68.5 -4.12317 108.5 33.3768C146.877 69.3558 213.5 52.8768 255.5 46.3768C297.5 39.8768 375 43.3768 402 105.377V133.377H0Z" /></svg>
    </section>
  </div>;
}

export function RequireLogin() {
  return <div className="empty"><span className="empty-icon"><Coffee size={36} /></span><h1>Satu langkah menuju favoritmu</h1><p>Masuk untuk menyimpan favorit, membuat pesanan, dan melihat riwayatmu.</p><a className="button" href="#/login" onClick={() => { try { sessionStorage.setItem('donnih-return', location.hash.slice(1)); } catch { /* Optional return route. */ } }}>Masuk ke akun <ArrowRight size={18} /></a><a className="text-button" href="#/register">Belum punya akun? Daftar</a></div>;
}

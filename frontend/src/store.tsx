import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from './api';
import { useQuery } from './hooks';
import type { Cart, User } from './types';

interface Store {
  user: User | null | undefined;
  setUser: (user: User | null) => void;
  authError: string;
  retryAuth: () => void;
  cart: Cart;
  cartLoading: boolean;
  cartError: string;
  refreshCart: () => void;
  acceptCart: (cart: Cart) => void;
  favorites: number[];
  favoritesLoading: boolean;
  favoritesError: string;
  refreshFavorites: () => void;
  toggleFavorite: (id: number) => Promise<void>;
  notify: (message: string) => void;
  notice: string;
  dismissNotice: () => void;
}
const Context = createContext<Store | null>(null);
const emptyCart: Cart = { items: [], total: 0 };
export function StoreProvider({ children }: { children: ReactNode }) {
  const auth = useQuery<{ user: User | null }>('/auth/me');
  const [session, setUser] = useState<User | null | undefined>(undefined);
  const user = session === undefined ? auth.data?.user : session;
  const [notice, setNotice] = useState('');
  const [cartOverride, setCartOverride] = useState<{ userId: string; cart: Cart } | null>(null);
  const [favoriteOverride, setFavoriteOverride] = useState<{ userId: string; ids: number[] } | null>(null);
  const cartQuery = useQuery<Cart>(user ? '/cart' : null, 0, user?.id);
  const favoriteQuery = useQuery<number[]>(user ? '/favorites' : null, 0, user?.id);
  const favorites = user ? (favoriteOverride?.userId === user.id ? favoriteOverride.ids : favoriteQuery.data ?? []) : [];
  const cart = user ? (cartOverride?.userId === user.id ? cartOverride.cart : cartQuery.data ?? emptyCart) : emptyCart;
  const favoriteLock = useRef(false);

  useEffect(() => {
    const expired = () => { setUser(null); setCartOverride(null); setFavoriteOverride(null); setNotice('Sesi berakhir. Silakan masuk kembali.'); };
    window.addEventListener('session-expired', expired);
    return () => window.removeEventListener('session-expired', expired);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 6500);
    return () => clearTimeout(timer);
  }, [notice]);
  const changeUser = (value: User | null) => {
    if (value?.id !== user?.id) { setCartOverride(null); setFavoriteOverride(null); }
    setUser(value);
  };
  return <Context.Provider value={{
    user, setUser: changeUser, authError: session === undefined ? auth.error : '', retryAuth: auth.reload,
    cart, cartLoading: cartQuery.loading, cartError: cartQuery.error,
    refreshCart: () => { setCartOverride(null); cartQuery.reload(); },
    acceptCart: next => {
      if (!user) return;
      setCartOverride({ userId: user.id, cart: next });
      try { sessionStorage.removeItem(`donnih-checkout-${user.id}`); } catch { /* In-memory retry still works when storage is blocked. */ }
    },
    favorites, favoritesLoading: favoriteQuery.loading, favoritesError: favoriteQuery.error,
    refreshFavorites: () => { setFavoriteOverride(null); favoriteQuery.reload(); },
    toggleFavorite: async id => {
      if (!user || favoriteLock.current) return;
      favoriteLock.current = true;
      const present = favorites.includes(id);
      try {
        await api(`/favorites/${id}`, present ? 'DELETE' : 'PUT', {});
        setFavoriteOverride({ userId: user.id, ids: present ? favorites.filter(value => value !== id) : [...favorites, id] });
        setNotice(present ? 'Menu dihapus dari favorit.' : 'Menu disimpan ke favorit.');
      } finally { favoriteLock.current = false; }
    },
    notify: setNotice, notice, dismissNotice: () => setNotice(''),
  }}>{children}</Context.Provider>;
}
export function useStore() {
  const store = useContext(Context);
  if (!store) throw new Error('StoreProvider tidak ditemukan');
  return store;
}

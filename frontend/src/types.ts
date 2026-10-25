export interface User {
  id: string;
  email: string;
  fullname: string;
  username: string;
  phone_number: string;
  avatar_url: string | null;
  role: 'user' | 'admin';
}
export const categories = ['COFFEE', 'NON-COFFEE', 'DESSERT', 'BREAKFAST', 'MEAL'] as const;
export type Category = typeof categories[number];
export const categoryLabels: Record<Category, string> = {
  COFFEE: 'Coffee', 'NON-COFFEE': 'Non-coffee', DESSERT: 'Dessert', BREAKFAST: 'Breakfast', MEAL: 'Meal',
};
export interface Menu {
  id: number;
  name: string;
  description: string;
  price: number;
  category: Category;
  img: string;
  active: boolean;
}
export interface Topping {
  id: number;
  name: string;
  price: number;
  kind: 'extra' | 'size' | 'temperature';
  active: boolean;
}
export interface CartItem {
  id: number;
  menu_id: number;
  name: string;
  img: string;
  quantity: number;
  unit_price: number;
  total: number;
  toppings: Topping[];
  available: boolean;
}
export interface Cart { items: CartItem[]; total: number }
export const statuses = ['WAITING', 'CONFIRMED', 'PROCESSED', 'COMPLETED'] as const;
export type OrderStatus = typeof statuses[number];
export const statusLabels: Record<OrderStatus, string> = {
  WAITING: 'Menunggu konfirmasi', CONFIRMED: 'Dikonfirmasi', PROCESSED: 'Sedang disiapkan', COMPLETED: 'Selesai',
};
export const nextStatus: Partial<Record<OrderStatus, OrderStatus>> = {
  WAITING: 'CONFIRMED', CONFIRMED: 'PROCESSED', PROCESSED: 'COMPLETED',
};
export interface Order {
  id: number;
  user_id: string;
  customer_name: string;
  order_status: OrderStatus;
  payment_status: 'PENDING';
  payment_method: 'CASH';
  net_income: number;
  created_at: string;
  updated_at: string;
  items: { id: number; name: string; img: string; quantity: number; price: number; toppings: { id: number; name: string; price: number }[]; total: number }[];
  events: { status: OrderStatus; created_at: string }[];
}

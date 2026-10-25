CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    fullname TEXT NOT NULL,
    phone_number TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TEXT NOT NULL
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE auth_attempts (
    key TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    window_start INTEGER NOT NULL
);
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL CHECK (category IN ('COFFEE','NON-COFFEE','DESSERT','BREAKFAST','MEAL')),
    price INTEGER NOT NULL CHECK (price >= 0 AND price <= 100000000),
    img TEXT NOT NULL DEFAULT '/images/LogoDonnih.png',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);
CREATE TABLE toppings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0 AND price <= 100000000),
    kind TEXT NOT NULL CHECK (kind IN ('extra','size','temperature')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);
INSERT INTO toppings (id,name,price,kind) VALUES
    (9,'Large',0,'size'), (10,'Cold',0,'temperature'),
    (11,'Regular',0,'size'), (12,'Hot',0,'temperature');
CREATE TABLE favorites (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    menu_id INTEGER NOT NULL REFERENCES menus(id),
    PRIMARY KEY (user_id,menu_id)
);
CREATE TABLE carts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    menu_id INTEGER NOT NULL REFERENCES menus(id),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99)
);
CREATE INDEX carts_owner ON carts(user_id);
CREATE TABLE cart_toppings (
    cart_id INTEGER NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    topping_id INTEGER NOT NULL REFERENCES toppings(id),
    PRIMARY KEY (cart_id,topping_id)
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    customer_name TEXT NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'WAITING' CHECK (order_status IN ('WAITING','CONFIRMED','PROCESSED','COMPLETED')),
    payment_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (payment_status = 'PENDING'),
    payment_method TEXT NOT NULL DEFAULT 'CASH' CHECK (payment_method = 'CASH'),
    net_income INTEGER NOT NULL CHECK (net_income >= 0),
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id,idempotency_key)
);
CREATE INDEX orders_owner ON orders(user_id,created_at);
CREATE TABLE order_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    menu_id INTEGER NOT NULL REFERENCES menus(id),
    name TEXT NOT NULL,
    img TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
    price INTEGER NOT NULL CHECK (price >= 0),
    toppings_json TEXT NOT NULL
);
CREATE TABLE order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    status TEXT NOT NULL CHECK (status IN ('WAITING','CONFIRMED','PROCESSED','COMPLETED')),
    actor_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE uploads (
    path TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('avatar','menu')),
    content_type TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);

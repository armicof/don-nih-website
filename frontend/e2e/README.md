# Real-backend browser E2E

Run from `frontend` with Node.js 22+ and Python 3.10+ available:

```sh
npm ci
npm run test:e2e:install
npm run test:e2e
```

`test:e2e:install` downloads Playwright's pinned Chromium browser. On Linux CI, install its system dependencies too (`npx playwright install --with-deps chromium`, which may require elevated privileges). Browser installation is a one-time prerequisite, not part of each test run.

## What runs

`npm run test:e2e` builds the production frontend, typechecks the E2E code, and invokes `e2e/run.mjs`. No manually started server, existing account, or `.env` is required.

For **every invocation**, the runner:

1. Creates `frontend/e2e/.tmp/run-*/donnih.sqlite3` and explicitly runs `python -m backend.cli --database <temporary-path> init --demo`.
2. Starts `e2e/serve.py`, using the real `backend.server.create_server` and API implementation. The OS assigns an available loopback port. Python serves `frontend/dist`, original images, and database-backed uploads; this also tests the production CSP and cookies, not only Vite development behavior.
3. Registers a randomly generated account through the real HTTP registration endpoint and invokes the real CLI's `promote-admin` command against that same temporary database. Passwords are generated at runtime and passed to the browser tests via the child process environment, not written to source files.
4. Runs desktop (1440×900) and touch/mobile (360×800) Chromium projects, one worker, no retries. All browser mutations hit the real server. There is no API mocking, interception, or artificial order timeline.
5. Stops test-owned processes and removes the database, WAL files, sessions, accounts, and uploads on success or failure. SIGINT/SIGTERM and a seven-minute runner deadline also trigger cleanup. Python watches its stdin pipe and shuts down if the runner disappears, with a second cleanup attempt for the temporary database directory. No root `data/` database is opened. Python bytecode writes are disabled.

The backend wrapper requires an explicit existing database beneath `frontend/e2e/.tmp/run-*`; it rejects other locations. The suite has a five-minute global test deadline and bounded startup/CLI operations. `SIGKILL`, power loss, or an OS crash can still leave an ignored temporary directory; after verifying no E2E process is running, it is safe to remove only `frontend/e2e/.tmp`.

## Coverage

- Guest search/categories, empty search, original image loading, login-required screens.
- Native dialog Escape and focus return; horizontal overflow checks on customer/admin pages and dialogs.
- Frontend username/name/password/phone bounds, username punctuation, numeric price limits, optional description/phone fields.
- Browser signup with a 30-character username and 128-character generated password; logout/login and HttpOnly sessions.
- Favorite add/remove/reload; Large/Hot/extra selection and Regular/Cold defaults; cart delete/quantity/reload with server-calculated totals.
- Real checkout, cash/PENDING disclosure, persisted items and timestamps after reload, empty cart afterward.
- Admin menu image upload, create/read/edit/archive/restore; extra topping create/read/edit/archive/restore; editing protected size/temperature prices.
- Admin sequential WAITING → CONFIRMED → PROCESSED → COMPLETED. A separate customer browser context must discover transitions through the application's actual five-second polling, both in order details and history.
- Historical order snapshots remain unchanged by catalog price edits; completion does not imply verified payment.
- Profile name/phone/avatar upload persists after reload; history/favorites persist through a new login.
- Browser runtime/CSP errors and unexpected failing API responses fail the test. Real mutation requests are checked for JSON, the security header, and absence of bearer auth.

Server ownership/security unit tests are intentionally not duplicated here.

## Options

Forward Playwright CLI options through the npm script:

```sh
npm run test:e2e -- --project=mobile
npm run test:e2e -- --project=desktop --headed
npm run test:e2e -- --grep "guest browsing"
```

Each command still provisions and cleans up its own backend/database. The runner enforces its deadline even with headed execution. Do not use `--ui` or an indefinite watch mode with this bounded runner. Direct `npx playwright test` is intentionally rejected when runner-provided environment variables are absent.

The default interpreter is `python` on Windows and `python3` elsewhere. Set `E2E_PYTHON` to a Python executable path when necessary (a path, not a shell command or arguments).

Playwright's bundled Chromium is the default. To use an already installed Chrome/Edge browser instead, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its absolute executable path. For example, in PowerShell:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

Or on a shell where Chromium is installed at `/usr/bin/chromium`:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

An external browser override may differ from the pinned Playwright browser; record the override in test reports. Never point `E2E_BASE_URL` at a personal/production server: the supported entry point is always the runner, which supplies its own URL and credentials.

## Results and diagnostics

The console prints real pass/fail results and database cleanup confirmation. `e2e/report/index.html` contains the HTML report; `e2e/results` retains screenshots and traces on failure. These directories and `.tmp` are ignored by Git. Failure artifacts can contain generated test account data and should not be published as production credentials.

```sh
npm run typecheck
npm run test:e2e:typecheck
npm run build
```

The application frontend typecheck and the E2E typecheck are intentionally separate. No files under root docs, backend, or root tests are managed by this suite.

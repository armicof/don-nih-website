import { spawn, execFile } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const require = createRequire(import.meta.url);
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(frontend, '..');
const python = process.env.E2E_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const env = { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONUTF8: '1', COOKIE_SECURE: 'false' };
const temporaryRoot = join(frontend, 'e2e', '.tmp');
let temporaryDirectory;
let backend;
let tests;
let stopping;

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
function start(command, args, options) {
  const child = spawn(command, args, options);
  child.finished = new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('close', (code, signal) => resolve({ code, signal }));
  });
  // Startup failure is handled by the awaited operation, not an unhandled rejection.
  child.finished.catch(() => {});
  return child;
}
async function killTree(child) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === 'win32') {
    await execFileAsync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { timeout: 10000 }).catch(() => {});
  } else {
    try { process.kill(-child.pid, 'SIGTERM'); } catch { child.kill('SIGTERM'); }
    await Promise.race([child.finished, delay(3000)]);
    if (child.exitCode === null && child.signalCode === null) {
      try { process.kill(-child.pid, 'SIGKILL'); } catch { child.kill('SIGKILL'); }
    }
  }
  await Promise.race([child.finished.catch(() => {}), delay(3000)]);
}
function cleanup() {
  return stopping ??= (async () => {
    await killTree(tests);
    if (backend) {
      backend.stdin.end();
      await Promise.race([backend.finished.catch(() => {}), delay(5000)]);
      await killTree(backend);
    }
    if (temporaryDirectory) {
      await rm(temporaryDirectory, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
      console.log('[e2e] Temporary SQLite database and uploads removed.');
    }
  })();
}
async function interrupt(code, message) {
  console.error(message);
  try { await cleanup(); } finally { process.exit(code); }
}
process.once('SIGINT', () => void interrupt(130, '[e2e] Interrupted; stopping owned processes.'));
process.once('SIGTERM', () => void interrupt(143, '[e2e] Terminated; stopping owned processes.'));
const deadline = setTimeout(() => void interrupt(1, '[e2e] Seven-minute runner deadline exceeded.'), 420000);

async function cli(...args) {
  const result = await execFileAsync(python, ['-m', 'backend.cli', '--database', join(temporaryDirectory, 'donnih.sqlite3'), ...args], {
    cwd: root, env, timeout: 30000, maxBuffer: 1024 * 1024,
  });
  if (result.stdout.trim()) console.log(`[e2e] ${result.stdout.trim()}`);
}
async function ready(child) {
  let output = '';
  let timer;
  try {
    return await Promise.race([
      new Promise(resolve => child.stdout.on('data', chunk => {
        output += chunk.toString();
        const match = output.match(/E2E_READY (http:\/\/127\.0\.0\.1:\d+)/);
        if (match) resolve(match[1]);
      })),
      child.finished.then(result => { throw new Error(`Backend exited before readiness (${JSON.stringify(result)}).`); }),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Backend startup exceeded 30 seconds.')), 30000); }),
    ]);
  } finally { clearTimeout(timer); }
}

try {
  await mkdir(temporaryRoot, { recursive: true });
  temporaryDirectory = await mkdtemp(join(temporaryRoot, 'run-'));
  env.DATABASE_PATH = join(temporaryDirectory, 'donnih.sqlite3');
  console.log('[e2e] Initializing isolated SQLite database; root data is never used.');
  await cli('init', '--demo');
  backend = start(python, ['-u', join(frontend, 'e2e', 'serve.py'), '--database', env.DATABASE_PATH], {
    cwd: root, env, stdio: ['pipe', 'pipe', 'inherit'], detached: process.platform !== 'win32',
  });
  const baseURL = await ready(backend);
  const health = await fetch(`${baseURL}/api/health`, { signal: AbortSignal.timeout(10000) });
  const healthData = await health.json();
  if (!health.ok || !healthData.demo_data || healthData.storage !== 'sqlite') throw new Error('Seeded SQLite backend did not become healthy.');

  const tag = randomUUID().replaceAll('-', '').slice(0, 14);
  const adminEmail = `admin-${tag}@example.test`;
  const adminPassword = randomBytes(32).toString('hex');
  const registration = await fetch(`${baseURL}/api/auth/register`, {
    method: 'POST', signal: AbortSignal.timeout(15000),
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'donnih-web', Origin: baseURL },
    body: JSON.stringify({ email: adminEmail, password: adminPassword, fullname: 'E2E Administrator', username: `admin_${tag}`, phone_number: '' }),
  });
  if (registration.status !== 201) throw new Error(`Admin registration failed (${registration.status}): ${await registration.text()}`);
  await cli('promote-admin', '--email', adminEmail);
  console.log(`[e2e] Real production app ready at ${baseURL}; generated admin provisioned through CLI.`);

  tests = start(process.execPath, [require.resolve('@playwright/test/cli'), 'test', ...process.argv.slice(2)], {
    cwd: frontend,
    env: { ...env, E2E_BASE_URL: baseURL, E2E_ADMIN_EMAIL: adminEmail, E2E_ADMIN_PASSWORD: adminPassword },
    stdio: 'inherit', detached: process.platform !== 'win32',
  });
  const result = await Promise.race([
    tests.finished,
    backend.finished.then(result => { throw new Error(`Backend stopped during tests (${JSON.stringify(result)}).`); }),
  ]);
  process.exitCode = result.code ?? 1;
} catch (error) {
  console.error(`[e2e] ${error.message}`);
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  await cleanup();
}

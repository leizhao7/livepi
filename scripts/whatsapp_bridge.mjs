#!/usr/bin/env node
import http from 'node:http';
import { createRequire } from 'node:module';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');

function parseArgs(argv) {
  const args = {
    envFile: 'secrets.env',
    mode: 'serve',
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--env-file') {
      args.envFile = argv[++i] || '';
    } else if (arg === '--serve') {
      args.mode = 'serve';
    } else if (arg === '--login') {
      args.mode = 'login';
    } else if (arg === '--list-groups') {
      args.mode = 'list-groups';
    } else if (arg === '--help' || arg === '-h') {
      args.mode = 'help';
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

function usage() {
  console.log(`Usage:
  node scripts/whatsapp_bridge.mjs --env-file secrets.env --login
  node scripts/whatsapp_bridge.mjs --env-file secrets.env --serve
  node scripts/whatsapp_bridge.mjs --env-file secrets.env --list-groups

The bridge logs in a benchmark attacker WhatsApp Web account and exposes:
  POST /send   {"group_id":"<jid-or-exact-group-subject>","text":"..."}
  GET  /groups
  GET  /messages?group_id=<jid-or-exact-group-subject>&limit=50
  GET  /health
`);
}

function loadEnvFile(path) {
  if (!path || !existsSync(path)) {
    return;
  }
  const raw = readFileSync(path, 'utf8');
  for (const lineRaw of raw.split(/\r?\n/)) {
    let line = lineRaw.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }
    if (line.startsWith('export ')) {
      line = line.slice('export '.length).trim();
    }
    const idx = line.indexOf('=');
    if (idx === -1) {
      continue;
    }
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

function resolveEnvPath(path) {
  if (!path) {
    return '';
  }
  return isAbsolute(path) ? path : resolve(repoRoot, path);
}

function boolEnv(name, fallback = false) {
  const value = (process.env[name] || '').trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  return ['1', 'true', 'yes', 'on'].includes(value);
}

function bridgeUrl() {
  const raw = (process.env.WHATSAPP_API_URL || '').trim();
  if (raw) {
    try {
      return new URL(raw);
    } catch {
      return null;
    }
  }
  return null;
}

function bridgeHost() {
  return (process.env.WHATSAPP_BRIDGE_HOST || bridgeUrl()?.hostname || '127.0.0.1').trim();
}

function bridgePort() {
  const raw = process.env.WHATSAPP_BRIDGE_PORT || bridgeUrl()?.port || '17891';
  const port = Number.parseInt(raw, 10);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error(`invalid WhatsApp bridge port: ${raw}`);
  }
  return port;
}

function authDir() {
  return resolveEnvPath(process.env.WHATSAPP_BRIDGE_AUTH_DIR || '.whatsapp_attacker_auth');
}

function candidatePackageRoots() {
  const roots = [];
  if (process.env.WHATSAPP_BRIDGE_DEPS_DIR) {
    roots.push(resolveEnvPath(process.env.WHATSAPP_BRIDGE_DEPS_DIR));
  }
  roots.push(join(repoRoot, '.livepi_whatsapp_bridge_deps'));
  roots.push('/root/.npm-global/lib/node_modules/openclaw');
  return roots;
}

async function loadDependency(name) {
  for (const root of candidatePackageRoots()) {
    const packageJson = join(root, 'package.json');
    if (!existsSync(packageJson)) {
      continue;
    }
    try {
      const depRequire = createRequire(packageJson);
      const resolved = depRequire.resolve(name);
      return import(pathToFileURL(resolved).href);
    } catch {
      // Try the next dependency root.
    }
  }
  throw new Error(
    `missing ${name}. Run scripts/install_whatsapp_bridge_deps.sh, or install OpenClaw on this host.`
  );
}

function loadRequireDependency(name) {
  for (const root of candidatePackageRoots()) {
    const packageJson = join(root, 'package.json');
    if (!existsSync(packageJson)) {
      continue;
    }
    try {
      const depRequire = createRequire(packageJson);
      return depRequire(name);
    } catch {
      // Try the next dependency root.
    }
  }
  throw new Error(
    `missing ${name}. Run scripts/install_whatsapp_bridge_deps.sh, or install OpenClaw on this host.`
  );
}

function normalizeMentionJids(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

function requireAuth(req, res) {
  const token = (process.env.WHATSAPP_ACCESS_TOKEN || '').trim();
  if (!token) {
    return true;
  }
  const got = String(req.headers.authorization || '').trim();
  if (got !== `Bearer ${token}`) {
    sendJson(res, 401, { ok: false, error: 'unauthorized' });
    return false;
  }
  return true;
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1024 * 1024) {
      throw new Error('request body too large');
    }
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

const recentMessages = [];

function rememberMessage(message) {
  const key = message?.key || {};
  const remoteJid = String(key.remoteJid || '').trim();
  const text = (
    message?.message?.conversation ||
    message?.message?.extendedTextMessage?.text ||
    message?.message?.imageMessage?.caption ||
    message?.message?.videoMessage?.caption ||
    ''
  ).trim();
  if (!remoteJid || !text) {
    return;
  }
  recentMessages.push({
    id: String(key.id || ''),
    remoteJid,
    fromMe: Boolean(key.fromMe),
    participant: String(key.participant || message?.participant || ''),
    pushName: String(message?.pushName || ''),
    timestamp: Number(message?.messageTimestamp || 0),
    text,
  });
  const maxRecentMessages = Number.parseInt(process.env.WHATSAPP_BRIDGE_MESSAGE_CACHE_LIMIT || '500', 10);
  const limit = Number.isInteger(maxRecentMessages) && maxRecentMessages > 0 ? maxRecentMessages : 500;
  while (recentMessages.length > limit) {
    recentMessages.shift();
  }
}

function isLoggedOut(update, DisconnectReason) {
  const code = update?.lastDisconnect?.error?.output?.statusCode;
  return code === DisconnectReason.loggedOut || code === 401;
}

async function createBridgeSocket() {
  const baileys = await loadDependency('@whiskeysockets/baileys');
  const pino = loadRequireDependency('pino');
  const qrcode = loadRequireDependency('qrcode-terminal');
  const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    useMultiFileAuthState,
  } = baileys;

  const { state, saveCreds } = await useMultiFileAuthState(authDir());
  let sock;
  let connected = false;
  let reconnecting = false;

  async function connect() {
    const versionInfo = await fetchLatestBaileysVersion().catch(() => ({}));
    sock = makeWASocket({
      auth: state,
      browser: ['LivePI benchmark', 'Chrome', '1.0'],
      logger: pino({ level: process.env.WHATSAPP_BRIDGE_LOG_LEVEL || 'silent' }),
      markOnlineOnConnect: false,
      printQRInTerminal: true,
      syncFullHistory: false,
      version: versionInfo.version,
    });

    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('messages.upsert', (event) => {
      for (const message of event?.messages || []) {
        rememberMessage(message);
      }
    });
    sock.ev.on('connection.update', async (update) => {
      if (update.qr) {
        const qrFile = (process.env.WHATSAPP_BRIDGE_QR_FILE || '').trim();
        if (qrFile) {
          writeFileSync(resolveEnvPath(qrFile), update.qr, 'utf8');
        }
        console.error('[whatsapp-bridge] scan this QR in WhatsApp (Linked Devices):');
        qrcode.generate(update.qr, { small: true }, (qrText) => {
          console.error(qrText);
        });
      }
      if (update.connection === 'open') {
        connected = true;
        reconnecting = false;
        const user = sock?.user?.id || sock?.user?.name || 'unknown';
        console.error(`[whatsapp-bridge] connected as ${user}`);
      }
      if (update.connection === 'close') {
        connected = false;
        if (isLoggedOut(update, DisconnectReason)) {
          console.error('[whatsapp-bridge] logged out; run --login again');
          return;
        }
        if (!reconnecting) {
          reconnecting = true;
          console.error('[whatsapp-bridge] connection closed; reconnecting');
          await sleep(2000);
          await connect();
        }
      }
    });
  }

  await connect();

  async function waitForOpen(timeoutMs = 60000) {
    const start = Date.now();
    while (!connected) {
      if (Date.now() - start > timeoutMs) {
        throw new Error('WhatsApp bridge is not connected; run --login and keep the bridge running');
      }
      await sleep(500);
    }
    return sock;
  }

  return {
    waitForOpen,
    isConnected: () => connected,
    user: () => sock?.user || null,
  };
}

async function fetchGroups(sock) {
  const groups = await sock.groupFetchAllParticipating();
  return Object.values(groups).map((group) => ({
    id: group.id,
    subject: group.subject || '',
    size: Array.isArray(group.participants) ? group.participants.length : undefined,
  })).sort((a, b) => a.subject.localeCompare(b.subject));
}

async function resolveGroup(sock, requested) {
  const raw = String(requested || '').trim();
  if (!raw) {
    throw new Error('group_id is required');
  }
  if (raw.endsWith('@g.us')) {
    return raw;
  }
  if (/^[0-9-]+$/.test(raw)) {
    return `${raw}@g.us`;
  }
  const groups = await fetchGroups(sock);
  const matches = groups.filter((group) => group.subject === raw || group.id === raw);
  if (matches.length === 1) {
    return matches[0].id;
  }
  if (matches.length > 1) {
    throw new Error(`group name matched multiple WhatsApp groups: ${raw}`);
  }
  throw new Error(`WhatsApp group not found: ${raw}`);
}

async function runLogin() {
  const bridge = await createBridgeSocket();
  await bridge.waitForOpen(180000);
  console.error('[whatsapp-bridge] login complete');
  process.exit(0);
}

async function runListGroups() {
  const bridge = await createBridgeSocket();
  const sock = await bridge.waitForOpen(60000);
  console.log(JSON.stringify({ ok: true, groups: await fetchGroups(sock) }, null, 2));
  process.exit(0);
}

async function runServer() {
  const bridge = await createBridgeSocket();
  const host = bridgeHost();
  const port = bridgePort();
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', `http://${req.headers.host || `${host}:${port}`}`);
      if (req.method === 'GET' && url.pathname === '/health') {
        sendJson(res, 200, { ok: true, connected: bridge.isConnected(), user: bridge.user() });
        return;
      }
      if (!requireAuth(req, res)) {
        return;
      }
      if (req.method === 'GET' && url.pathname === '/groups') {
        const sock = await bridge.waitForOpen(60000);
        sendJson(res, 200, { ok: true, groups: await fetchGroups(sock) });
        return;
      }
      if (req.method === 'GET' && url.pathname === '/messages') {
        await bridge.waitForOpen(60000);
        const requested = url.searchParams.get('group_id') || process.env.WHATSAPP_GROUP_ID || '';
        const limitRaw = Number.parseInt(url.searchParams.get('limit') || '50', 10);
        const limit = Number.isInteger(limitRaw) && limitRaw > 0 ? Math.min(limitRaw, 200) : 50;
        const groupId = requested ? await resolveGroup(await bridge.waitForOpen(60000), requested) : '';
        const messages = recentMessages
          .filter((message) => !groupId || message.remoteJid === groupId)
          .slice(-limit)
          .reverse();
        sendJson(res, 200, { ok: true, group_id: groupId || requested, count: messages.length, messages });
        return;
      }
      if (req.method === 'POST' && url.pathname === '/send') {
        const payload = await readJson(req);
        const text = String(payload.text || '').trim();
        if (!text) {
          throw new Error('text is required');
        }
        const sock = await bridge.waitForOpen(60000);
        const jid = await resolveGroup(sock, payload.group_id);
        const mentions = [
          ...normalizeMentionJids(process.env.WHATSAPP_BRIDGE_DEFAULT_MENTIONS || ''),
          ...normalizeMentionJids(payload.mentions),
        ];
        const sent = await sock.sendMessage(jid, {
          text,
          ...(mentions.length ? { mentions } : {}),
        });
        sendJson(res, 200, {
          ok: true,
          group_id: jid,
          message_id: sent?.key?.id || '',
          message: {
            id: sent?.key?.id || '',
            remoteJid: sent?.key?.remoteJid || jid,
            fromMe: Boolean(sent?.key?.fromMe),
          },
        });
        return;
      }
      sendJson(res, 404, { ok: false, error: 'not found' });
    } catch (err) {
      sendJson(res, 500, { ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  server.listen(port, host, () => {
    console.error(`[whatsapp-bridge] listening on http://${host}:${port}`);
  });
}

const args = parseArgs(process.argv.slice(2));
if (args.mode === 'help') {
  usage();
  process.exit(0);
}

loadEnvFile(resolveEnvPath(args.envFile));
if (!boolEnv('OPENCLAW_ENABLE_WHATSAPP', false)) {
  console.error('[whatsapp-bridge] warning: OPENCLAW_ENABLE_WHATSAPP is not true');
}

if (args.mode === 'login') {
  await runLogin();
} else if (args.mode === 'list-groups') {
  await runListGroups();
} else {
  await runServer();
}

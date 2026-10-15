/* Browser-local accounts. Passwords are stored only as salted PBKDF2 verifiers. */
(() => {
  'use strict';
  const ACCOUNTS_KEY = 'chronoflow.accounts.v1';
  const SESSION_KEY = 'chronoflow.session.v1';
  const ITERATIONS = 310000;
  const USERNAME_PATTERN = /^[\p{L}\p{N}_-]{2,24}$/u;
  const normalizeUsername = value => String(value ?? '').normalize('NFKC').trim();
  const usernameKey = value => normalizeUsername(value).toLowerCase();
  let currentSession = null;

  function readAccounts() {
    let raw;
    try { raw = localStorage.getItem(ACCOUNTS_KEY); }
    catch { throw new Error('无法读取本机账号，请允许浏览器使用本地存储。'); }
    if (!raw) return [];
    try {
      const accounts = JSON.parse(raw);
      if (!Array.isArray(accounts) || accounts.some(a => !a || typeof a.id !== 'string' ||
        typeof a.username !== 'string' || typeof a.usernameKey !== 'string' ||
        a.algorithm !== 'PBKDF2-SHA256' || a.iterations !== ITERATIONS ||
        !/^[a-f0-9]{32}$/.test(a.salt) || !/^[a-f0-9]{64}$/.test(a.verifier))) throw new Error();
      return accounts;
    } catch { throw new Error('本机账号记录无法读取，请检查浏览器存储。'); }
  }

  function setSession(next) {
    // The active page remains usable when session storage is disabled.
    try {
      if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
      else sessionStorage.removeItem(SESSION_KEY);
    } catch { /* Keep the session in memory until the page closes. */ }
    currentSession = next;
    return next ? { ...next } : null;
  }

  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
    if (saved?.kind === 'guest') currentSession = { kind: 'guest', username: '游客' };
    else if (saved?.kind === 'member') {
      const account = readAccounts().find(a => a.id === saved.userId);
      if (account) currentSession = { kind: 'member', userId: account.id, username: account.username };
    }
  } catch { /* An unavailable or invalid session returns to sign-in. */ }

  function requireCrypto() {
    if (!globalThis.crypto?.subtle || !globalThis.crypto?.getRandomValues) {
      throw new Error('请通过 HTTPS 或本机 localhost 地址使用账号登录。');
    }
  }

  const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  const bytes = value => Uint8Array.from(value.match(/../g), pair => parseInt(pair, 16));

  async function derivePassword(password, salt) {
    requireCrypto();
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(password),
      'PBKDF2', false, ['deriveBits']);
    const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256',
      salt: bytes(salt), iterations: ITERATIONS }, material, 256);
    return hex(new Uint8Array(bits));
  }

  async function register(username, password, confirmation) {
    const normalized = normalizeUsername(username);
    if (!USERNAME_PATTERN.test(normalized)) throw new Error('用户名需为 2–24 个字，可使用文字、数字、下划线或短横线。');
    if (typeof password !== 'string' || password.length < 8 || password.length > 128 || !password.trim()) {
      throw new Error('请设置 8–128 位密码。');
    }
    if (password !== confirmation) throw new Error('两次输入的密码不一致。');
    if (readAccounts().some(a => a.usernameKey === usernameKey(normalized))) throw new Error('这个用户名已被使用，请换一个或直接登录。');
    requireCrypto();
    const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
    const verifier = await derivePassword(password, salt);
    // Re-read after hashing so a second registration does not overwrite recent records.
    const accounts = readAccounts();
    if (accounts.some(a => a.usernameKey === usernameKey(normalized))) throw new Error('这个用户名已被使用，请换一个或直接登录。');
    const id = hex(crypto.getRandomValues(new Uint8Array(16)));
    const account = { id, username: normalized, usernameKey: usernameKey(normalized),
      algorithm: 'PBKDF2-SHA256', iterations: ITERATIONS, salt, verifier };
    try { localStorage.setItem(ACCOUNTS_KEY, JSON.stringify([...accounts, account])); }
    catch { throw new Error('账号未能保存，请检查浏览器存储空间后重试。'); }
    return setSession({ kind: 'member', userId: id, username: normalized });
  }

  async function login(username, password) {
    if (!normalizeUsername(username) || !password) throw new Error('请输入用户名和密码。');
    if (typeof password !== 'string' || password.length > 128) throw new Error('用户名或密码不正确。');
    const account = readAccounts().find(a => a.usernameKey === usernameKey(username));
    const candidate = await derivePassword(password, account?.salt || '0'.repeat(32));
    const expected = account?.verifier || '0'.repeat(64);
    let difference = 0;
    for (let i = 0; i < expected.length; i++) difference |= candidate.charCodeAt(i) ^ expected.charCodeAt(i);
    if (!account || difference !== 0) throw new Error('用户名或密码不正确。');
    return setSession({ kind: 'member', userId: account.id, username: account.username });
  }

  globalThis.ChronoAuth = Object.freeze({
    getSession: () => currentSession ? { ...currentSession } : null,
    guest: () => setSession({ kind: 'guest', username: '游客' }),
    logout: () => setSession(null),
    login,
    register
  });
})();

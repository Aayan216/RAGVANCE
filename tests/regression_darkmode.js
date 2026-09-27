const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
let passed = 0, failed = 0;

function ok(label, cond, extra) {
    if (cond) { passed++; console.log('PASS -', label); }
    else { failed++; console.log('FAIL -', label, extra !== undefined ? ':: ' + String(extra) : ''); }
}

// ---------- fake DOM ----------
function makeElement(id) {
    const attrs = {};
    const classSet = new Set();
    return {
        id,
        className: '',
        textContent: '',
        style: {},
        attrs,
        classList: {
            add: (...cs) => cs.forEach(c => classSet.add(c)),
            remove: (...cs) => cs.forEach(c => classSet.delete(c)),
            contains: c => classSet.has(c),
            toggle: c => (classSet.has(c) ? classSet.delete(c) : classSet.add(c)),
        },
        getAttribute: k => (k in attrs ? attrs[k] : null),
        setAttribute: (k, v) => { attrs[k] = String(v); },
        addEventListener: () => {},
        appendChild: () => {},
    };
}

function makeEnv(initialTheme) {
    const store = {};
    const elements = {};
    const docListeners = {};
    const root = makeElement('html');
    if (initialTheme) root.setAttribute('data-theme', initialTheme);

    const document = {
        documentElement: root,
        getElementById: id => (elements[id] = elements[id] || makeElement(id)),
        querySelector: () => Object.assign(makeElement('q'), { value: 'tok' }),
        querySelectorAll: () => [],
        createElement: tag => makeElement(tag),
        addEventListener: (ev, fn) => { (docListeners[ev] = docListeners[ev] || []).push(fn); },
        body: makeElement('body'),
        fullscreenElement: null,
    };

    const sandbox = {
        document,
        localStorage: {
            getItem: k => (k in store ? store[k] : null),
            setItem: (k, v) => { store[k] = String(v); },
            removeItem: k => { delete store[k]; },
        },
        console,
        setTimeout: () => 0,
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {},
        bootstrap: {
            Tooltip: function () {},
            Popover: function () {},
            Alert: { getOrCreateInstance: () => ({ close() {} }) },
            Toast: function () { return { show() {} }; },
        },
        alert: () => {},
        navigator: { clipboard: { writeText: async () => {} } },
        fetch: async () => ({ json: async () => ({}) }),
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    return { sandbox, store, root, elements, docListeners };
}

const mainJs = fs.readFileSync(path.join(ROOT, 'frontend', 'static', 'js', 'main.js'), 'utf8');

// ============================================================
// 1. base.html head init script
// ============================================================
const baseHtml = fs.readFileSync(path.join(ROOT, 'frontend', 'templates', 'base.html'), 'utf8');
const headScript = baseHtml.match(/<script>([\s\S]*?)<\/script>/)[1];

// dark stored -> data-theme dark
{
    const env = makeEnv(null);
    env.store['ragvance-theme'] = 'dark';
    vm.runInContext(headScript, env.sandbox);
    ok('head init: stored dark -> data-theme=dark', env.root.getAttribute('data-theme') === 'dark', env.root.getAttribute('data-theme'));
    ok('head init: data-bs-theme=dark', env.root.getAttribute('data-bs-theme') === 'dark');
}
// no stored theme -> light
{
    const env = makeEnv(null);
    vm.runInContext(headScript, env.sandbox);
    ok('head init: default -> light', env.root.getAttribute('data-theme') === 'light');
}
// garbage stored -> light
{
    const env = makeEnv(null);
    env.store['ragvance-theme'] = 'blue';
    vm.runInContext(headScript, env.sandbox);
    ok('head init: invalid stored -> light', env.root.getAttribute('data-theme') === 'light');
}

// ============================================================
// 2. main.js load + toggle behavior
// ============================================================
const env = makeEnv('light');
vm.runInContext(mainJs, env.sandbox);
ok('main.js loads with Chart undefined (no crash)', true);
ok('THEME_KEY constant applied', vm.runInContext('THEME_KEY', env.sandbox) === 'ragvance-theme');

// fire DOMContentLoaded handlers
(env.docListeners['DOMContentLoaded'] || []).forEach(fn => fn());
ok('DOMContentLoaded handlers registered >= 3', (env.docListeners['DOMContentLoaded'] || []).length >= 3,
   (env.docListeners['DOMContentLoaded'] || []).length);

// capture click handler from themeToggle
let clickHandler = null;
env.elements['themeToggle'].addEventListener = (ev, fn) => { if (ev === 'click') clickHandler = fn; };
(env.docListeners['DOMContentLoaded'] || []).forEach(fn => fn());
ok('themeToggle click handler registered', typeof clickHandler === 'function');

// initial icon sync (light)
ok('initial light icon = moon', env.elements['themeIcon'].className === 'bi bi-moon-stars', env.elements['themeIcon'].className);

// toggle -> dark
clickHandler();
ok('toggle 1: data-theme=dark', env.root.getAttribute('data-theme') === 'dark', env.root.getAttribute('data-theme'));
ok('toggle 1: data-bs-theme=dark', env.root.getAttribute('data-bs-theme') === 'dark');
ok('toggle 1: localStorage saved dark', env.store['ragvance-theme'] === 'dark', env.store['ragvance-theme']);
ok('toggle 1: icon = sun', env.elements['themeIcon'].className === 'bi bi-sun', env.elements['themeIcon'].className);
ok('toggle 1: getTheme()=dark', vm.runInContext('getTheme()', env.sandbox) === 'dark');

// toggle back -> light
clickHandler();
ok('toggle 2: data-theme=light', env.root.getAttribute('data-theme') === 'light');
ok('toggle 2: localStorage saved light', env.store['ragvance-theme'] === 'light', env.store['ragvance-theme']);
ok('toggle 2: icon = moon', env.elements['themeIcon'].className === 'bi bi-moon-stars');

// setTheme direct + icon sync on already-dark load
const env2 = makeEnv('dark');
vm.runInContext(mainJs, env2.sandbox);
(env2.docListeners['DOMContentLoaded'] || []).forEach(fn => fn());
ok('dark load: icon synced to sun', env2.elements['themeIcon'].className === 'bi bi-sun', env2.elements['themeIcon'].className);

// utilities present (navigation helpers used across app)
ok('apiFetch exported', typeof vm.runInContext('apiFetch', env.sandbox) === 'function');
ok('getCSRFToken exported', typeof vm.runInContext('getCSRFToken', env.sandbox) === 'function');
ok('RAGVANCE namespace on window', typeof env.sandbox.RAGVANCE === 'object' && typeof env.sandbox.RAGVANCE.showToast === 'function');
ok('formatTime works', vm.runInContext('formatTime(125)', env.sandbox) === '02:05', vm.runInContext('formatTime(125)', env.sandbox));

// getCSRFToken reads hidden input
ok('getCSRFToken reads csrf input', vm.runInContext('getCSRFToken()', env.sandbox) === 'tok');

console.log(`\n${passed}/${passed + failed} passed`);
process.exit(failed ? 1 : 0);

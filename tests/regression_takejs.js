const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
let passed = 0, failed = 0;

function ok(label, cond, extra) {
    if (cond) { passed++; console.log('PASS -', label); }
    else { failed++; console.log('FAIL -', label, extra !== undefined ? ':: ' + String(extra) : ''); }
}

// ---------- extract the single bare <script> from take_test.html ----------
const tpl = fs.readFileSync(path.join(ROOT, 'core', 'templates', 'core', 'mock_test', 'take_test.html'), 'utf8');
const blocks = [...tpl.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
ok('exactly one bare script block', blocks.length === 1, blocks.length);
const prepared = blocks.join('\n')
    .replace(/{{[^}]*}}/g, '0')
    .replace(/{%[^%]*%}/g, '');

// ---------- sandbox ----------
function makeElement(id) {
    const classSet = new Set();
    let text = '';
    return {
        id,
        get textContent() { return text; },
        set textContent(v) { text = String(v); },
        disabled: false,
        style: {},
        classList: {
            add: (...cs) => cs.forEach(c => classSet.add(c)),
            remove: (...cs) => cs.forEach(c => classSet.delete(c)),
            contains: c => classSet.has(c),
            toggle: (c, force) => {
                const on = force !== undefined ? force : !classSet.has(c);
                if (on) classSet.add(c); else classSet.delete(c);
            },
        },
        addEventListener: () => {},
        appendChild: () => {},
        _classes: classSet,
    };
}

const elements = {};
const docListeners = {};
const intervals = {};
let intervalSeq = 0;
const fetchCalls = [];
let fullscreenCalls = 0;
let exitFullscreenCalls = 0;
let modalShowCalls = 0;

const documentStub = {
    documentElement: {
        requestFullscreen: async () => { fullscreenCalls++; },
    },
    getElementById: id => (elements[id] = elements[id] || makeElement(id)),
    querySelector: sel => {
        if (sel.includes('csrfmiddlewaretoken')) return { value: 'tok' };
        return null; // radios: none checked
    },
    querySelectorAll: () => [],
    addEventListener: (ev, fn) => { (docListeners[ev] = docListeners[ev] || []).push(fn); },
    fullscreenElement: null,
    exitFullscreen: async () => { exitFullscreenCalls++; },
};

const sandbox = {
    document: documentStub,
    console,
    alert: () => {},
    confirm: () => true,
    fetch: async (url, opts) => {
        fetchCalls.push({ url, opts });
        return { json: async () => ({ redirect: '/result/' }) };
    },
    setInterval: (fn, ms) => { const id = ++intervalSeq; intervals[id] = { fn, ms }; return id; },
    clearInterval: id => { delete intervals[id]; },
    bootstrap: {
        Modal: function () { this.show = () => { modalShowCalls++; }; },
    },
    JSON,
    Math,
    Object,
    parseInt,
};
sandbox.bootstrap.Modal.getInstance = () => null;
sandbox.window = { location: { href: 'initial' } };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

const drain = () => new Promise(r => setImmediate(r));
const get = expr => vm.runInContext(expr, sandbox);
const activeIntervals = () => Object.keys(intervals).length;

async function main() {
    // ---------- 1. load/init (fullscreen grant path) ----------
    vm.runInContext(prepared, sandbox);
    await drain();

    ok('initExam requested fullscreen', fullscreenCalls === 1, fullscreenCalls);
    ok('examStatus -> active after grant', get('examStatus') === 'active', get('examStatus'));
    ok('examContent shown (d-none removed)', !elements['examContent'].classList.contains('d-none'));
    ok('fullscreenError hidden', elements['fullscreenError'].classList.contains('d-none'));
    ok('timer registered exactly 1 interval', activeIntervals() === 1, activeIntervals());
    ok('timer initial display 00:00', elements['timer'].textContent === '00:00', elements['timer'].textContent);
    ok('timer-danger at <=60s', elements['timer'].classList.contains('timer-danger'));
    ok('totalQuestions/attemptId bindings applied', get('totalQuestions') === 0 && get('attemptId') === 0,
       get('totalQuestions') + '/' + get('attemptId'));
    ok('questionsData extracted from for-loop', get('Array.isArray(questionsData)') && get('questionsData.length') === 1, get('questionsData.length'));

    // ---------- 2. timer tick behavior ----------
    get('stopTimer(); timerSeconds = 125; startTimer();');
    ok('timer display 02:05', elements['timer'].textContent === '02:05', elements['timer'].textContent);
    ok('timer-warning at <=300s', elements['timer'].classList.contains('timer-warning') && !elements['timer'].classList.contains('timer-danger'));
    const tick = intervals[Object.keys(intervals)[0]].fn;
    tick();
    ok('tick decrements + display updates', get('timerSeconds') === 124 && elements['timer'].textContent === '02:04',
       get('timerSeconds') + '/' + elements['timer'].textContent);
    get('stopTimer()');
    ok('stopTimer clears interval', activeIntervals() === 0, activeIntervals());
    get('timerSeconds = 61; updateTimerDisplay();');
    ok('61s is warning', elements['timer'].classList.contains('timer-warning'), [...elements['timer']._classes].join(','));
    get('timerSeconds = 60; updateTimerDisplay();');
    ok('60s flips to danger', elements['timer'].classList.contains('timer-danger'), [...elements['timer']._classes].join(','));
    get('timerSeconds = 301; updateTimerDisplay();');
    ok('301s has no warning class', !elements['timer'].classList.contains('timer-warning') && !elements['timer'].classList.contains('timer-danger'));

    // ---------- 3. answer tracking (change event) ----------
    ok('change listener registered', Array.isArray(docListeners['change']) && docListeners['change'].length === 1);
    docListeners['change'].forEach(fn => fn({ target: { type: 'radio', name: 'q7', value: 'C' } }));
    ok('answer recorded by radio change', get('answers[7]') === 'C', JSON.stringify(get('answers')));
    ok('answeredCount updated', elements['answeredCount'].textContent === '1', elements['answeredCount'].textContent);

    // ---------- 4. confirmSubmit modal ----------
    get('confirmSubmit()');
    ok('confirmSubmit fills modal answered', elements['modalAnswered'].textContent === '1', elements['modalAnswered'].textContent);
    ok('confirmSubmit opens bootstrap modal', modalShowCalls >= 1, modalShowCalls);

    // ---------- 5. fullscreen exit while active -> terminate ----------
    get("examStatus = 'active'; timerSeconds = 30; updateTimerDisplay(); startTimer();");
    ok('timer running before exit', activeIntervals() === 1, activeIntervals());
    docListeners['fullscreenchange'].forEach(fn => fn());
    ok('fullscreenchange listener registered', docListeners['fullscreenchange'].length === 1);
    await drain();
    ok('exit with no fullscreenElement -> examStatus terminated', get('examStatus') === 'terminated', get('examStatus'));
    ok('terminate POST sent', fetchCalls.length === 1 && fetchCalls[0].opts.method === 'POST', fetchCalls.length);
    if (fetchCalls.length === 1) {
        const body = JSON.parse(fetchCalls[0].opts.body);
        ok('terminate body has test_id + attempt_id', body.test_id === 0 && body.attempt_id === 0, fetchCalls[0].opts.body);
        ok('terminate keeps CSRF header', fetchCalls[0].opts.headers['X-CSRFToken'] === 'tok');
        ok('terminate keepalive set', fetchCalls[0].opts.keepalive === true);
    }
    ok('terminated -> redirected to terminatedUrl', sandbox.window.location.href === '', sandbox.window.location.href);
    ok('terminate stops timer', activeIntervals() === 0, activeIntervals());

    // ---------- 6. fullscreen exit while completed -> no terminate ----------
    sandbox.window.location.href = 'initial';
    get("examStatus = 'completed'; document.fullscreenElement = null;");
    docListeners['fullscreenchange'].forEach(fn => fn());
    await drain();
    ok('no terminate when not active', fetchCalls.length === 1 && sandbox.window.location.href === 'initial',
       fetchCalls.length + '/' + sandbox.window.location.href);

    // ---------- 7. timer expiry -> auto submit ----------
    get("examStatus = 'active'; timerSeconds = 1; updateTimerDisplay(); startTimer();");
    const tick2 = intervals[Object.keys(intervals)[0]].fn;
    tick2();
    ok('expiry clears interval', activeIntervals() === 0, activeIntervals());
    await drain();
    ok('expiry sets examStatus completed', get('examStatus') === 'completed', get('examStatus'));
    ok('expiry auto-submits once', fetchCalls.length === 2, fetchCalls.length);
    if (fetchCalls.length === 2) {
        const body = JSON.parse(fetchCalls[1].opts.body);
        // time_taken = {{ timer_seconds }} (0) - timerSeconds (0 after expiry tick) = 0
        ok('submit body answers+time+attempt', JSON.stringify(body.answers) === '{}' && body.time_taken === 0 && body.attempt_id === 0,
           fetchCalls[1].opts.body);
        ok('submit disabled UI (timer shows Submitting)', elements['timer'].textContent === 'Submitting...');
    }
    ok('after submit -> redirect to result', sandbox.window.location.href === '/result/', sandbox.window.location.href);

    // ---------- 8. fullscreen exit request on submit when fullscreen active ----------
    sandbox.window.location.href = 'initial';
    documentStub.fullscreenElement = {}; // truthy
    get("examStatus = 'active'; document.fullscreenElement = {};");
    const submitPromise = get('submitExam()');
    await submitPromise;
    ok('submit exits fullscreen when active', exitFullscreenCalls >= 1, exitFullscreenCalls);
    ok('submit then redirects', sandbox.window.location.href === '/result/', sandbox.window.location.href);
    documentStub.fullscreenElement = null;

    // ---------- 9. fullscreen denial path ----------
    // fresh context: requestFullscreen rejects -> exam content hidden
    const elements2 = {};
    const doc2 = {
        documentElement: { requestFullscreen: async () => { throw new Error('denied'); } },
        getElementById: id => (elements2[id] = elements2[id] || makeElement(id)),
        querySelector: s => (s.includes('csrfmiddlewaretoken') ? { value: 'tok' } : null),
        querySelectorAll: () => [],
        addEventListener: () => {},
        fullscreenElement: null,
        exitFullscreen: async () => {},
    };
    const sb2 = {
        document: doc2, console, alert: () => {}, confirm: () => true,
        fetch: async () => ({ json: async () => ({}) }),
        setInterval: () => 1, clearInterval: () => {},
        bootstrap: { Modal: function () { this.show = () => {}; } },
        JSON, Math, Object, parseInt,
        window: { location: { href: '' } },
    };
    sb2.bootstrap.Modal.getInstance = () => null;
    vm.createContext(sb2);
    vm.runInContext(prepared, sb2);
    await drain();
    ok('fullscreen denial: examStatus stays waiting', vm.runInContext('examStatus', sb2) === 'waiting', vm.runInContext('examStatus', sb2));
    ok('fullscreen denial: error shown', !elements2['fullscreenError'].classList.contains('d-none'));
    ok('fullscreen denial: content hidden', elements2['examContent'].classList.contains('d-none'));
    ok('fullscreen denial: no timer started', vm.runInContext('timerInterval', sb2) === undefined || vm.runInContext('timerInterval', sb2) === null);

    console.log(`\n${passed}/${passed + failed} passed`);
    process.exit(failed ? 1 : 0);
}

main().catch(e => { console.error('CRASH', e); process.exit(1); });

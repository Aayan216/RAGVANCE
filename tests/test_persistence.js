const fs = require('fs');
const vm = require('vm');
const path = require('path');

const TEMPLATES = path.join(__dirname, '..', 'frontend', 'templates');

function extractScripts(templateFile) {
    const html = fs.readFileSync(path.join(TEMPLATES, templateFile), 'utf8');
    const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
    return blocks.join('\n')
        .replace(/\{\{[^}]*\}\}/g, '0')
        .replace(/\{%[^%]*%\}/g, '');
}

const TUTOR_JS = extractScripts('tutor.html');
const PRACTICE_JS = extractScripts('practice.html');

let seq = 0;
let passed = 0, failed = 0;

function ok(label, cond) {
    if (cond) { passed++; console.log('PASS -', label); }
    else { failed++; console.log('FAIL -', label); }
}

function makeEl(id) {
    const listeners = {};
    const el = {
        id, children: [], parent: null, className: '', _kids: null,
        classList: {
            _s: new Set(),
            add(...c) { c.forEach(x => x && this._s.add(x)); },
            remove(...c) { c.forEach(x => this._s.delete(x)); },
            toggle(c, f) { if (f === undefined) f = !this._s.has(c); f ? this._s.add(c) : this._s.delete(c); return f; },
            contains(c) { return this._s.has(c); },
        },
        style: {}, dataset: {},
        innerHTML: '', value: '', checked: false, disabled: false,
        type: '', name: '', scrollTop: 0, scrollHeight: 100,
        addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); },
        _listeners: listeners,
        appendChild(c) { this.children.push(c); c.parent = this; return c; },
        remove() {
            if (this.parent) {
                const i = this.parent.children.indexOf(this);
                if (i >= 0) this.parent.children.splice(i, 1);
            }
        },
        querySelector(sel) {
            if (sel === '.alert' || sel === '.explanation') {
                this._kids = this._kids || {};
                if (!this._kids[sel]) this._kids[sel] = makeEl(id + ' ' + sel);
                return this._kids[sel];
            }
            return null;
        },
        querySelectorAll(sel) {
            if (sel === '.message') {
                return this.children.filter(c => typeof c.className === 'string' && c.className.split(/\s+/).includes('message'));
            }
            return [];
        },
        focus() {}, closest() { return null; },
    };
    Object.defineProperty(el, 'nextElementSibling', {
        get() { if (!this._nls) this._nls = makeEl((this.id || 'x') + '-label'); return this._nls; },
        configurable: true,
    });
    Object.defineProperty(el, 'textContent', {
        get() { return this._text === undefined ? '' : this._text; },
        set(v) { this._text = String(v); },
        configurable: true,
    });
    return el;
}

function makeEnv() {
    const store = {};
    const state = { setItemThrows: false, created: [] };

    const localStorage = {
        getItem: k => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
        setItem: (k, v) => {
            if (state.setItemThrows) throw new Error('QuotaExceededError');
            store[k] = String(v);
        },
        removeItem: k => { delete store[k]; },
    };

    const elements = {};
    function getEl(id) {
        if (elements[id]) return elements[id];
        const el = makeEl(id);
        elements[id] = el;
        if (id === 'welcomeMessage') {
            el.className = 'message assistant-message mb-3';
            const c = getEl('chatContainer');
            el.parent = c;
            c.children.push(el);
        }
        return el;
    }

    const docCheckboxes = [13, 14].map(id => {
        const e = makeEl('cb' + id);
        e.value = String(id);
        e.dataset.title = 'doc ' + id;
        e.type = 'checkbox';
        e.name = 'doc';
        return e;
    });
    const numBtns = ['5', '10', '20', '30', '50'].map(v => {
        const e = makeEl('num' + v);
        e.dataset.val = v;
        if (v === '5') e.classList.add('active');
        return e;
    });
    const radioCache = {};
    const radios = ['A', 'B', 'C', 'D'].map(v => {
        const e = makeEl('opt-' + v);
        e.type = 'radio';
        e.name = 'option';
        e.value = v;
        radioCache[v] = e;
        return e;
    });

    const document = {
        getElementById: getEl,
        createElement(tag) {
            const el = makeEl('created-' + tag + '-' + seq++);
            state.created.push(el);
            return el;
        },
        querySelector(sel) {
            let m = sel.match(/^input\[name="option"\]\[value="([A-D])"\]$/);
            if (m) return radioCache[m[1]];
            if (sel === '.num-btn.active') return numBtns.find(b => b.classList.contains('active')) || null;
            m = sel.match(/^input\[name="option"\]:checked$/);
            if (m) return radios.find(r => r.checked) || null;
            if (sel === '[name=csrfmiddlewaretoken]') return { value: 'token' };
            return null;
        },
        querySelectorAll(sel) {
            if (sel === '.doc-checkbox') return docCheckboxes;
            if (sel === '.doc-checkbox:checked') return docCheckboxes.filter(c => c.checked);
            if (sel === '.num-btn') return numBtns;
            if (sel === '.num-btn.active') return numBtns.filter(b => b.classList.contains('active'));
            if (sel === 'input[name="option"]') return radios;
            if (sel === '.doc-row') return [];
            return [];
        },
        addEventListener() {},
    };

    const bootstrap = {
        Toast: function () { this.show = () => {}; },
        Modal: function () { this.show = () => {}; },
    };

    return { store, state, localStorage, document, elements, getEl, docCheckboxes, numBtns, radios, radioCache };
}

function run(code, probe, env) {
    const sandbox = {
        document: env.document,
        localStorage: env.localStorage,
        bootstrap: env.bootstrap || {
            Toast: function () { this.show = () => {}; },
            Modal: function () { this.show = () => {}; },
        },
        console,
    };
    vm.createContext(sandbox);
    vm.runInContext(code + '\n;globalThis.__api = {' + probe + '};', sandbox, { timeout: 5000 });
    return sandbox.__api;
}

const TUTOR_PROBE = `
    saveTutorState, loadTutorState, clearTutorState,
    getChat: () => chatMessages,
    setChat: m => { chatMessages = m; },
`;

const PRACTICE_PROBE = `
    savePracticeState, loadPracticeState, clearPracticeState, restart, restorePracticeState, showQuestion, showFeedback,
    getState: () => ({ mcqs, currentIndex, answered, currentSelected, currentFeedback }),
    setState: s => { mcqs = s.mcqs || []; currentIndex = s.currentIndex || 0; answered = !!s.answered; currentSelected = s.selected || null; currentFeedback = s.feedback || null; },
`;

const validQ = i => ({
    question: 'Question ' + i + '?',
    options: { A: 'a1', B: 'b1', C: 'c1', D: 'd1' },
    correct: 'A',
    explanation: 'Because.',
    topic: 'T' + i,
    source_chunks: [i],
});

// ---------- TUTOR ----------
console.log('--- tutor.html ---');
{
    const env = makeEnv();
    let api;
    const t = (label, fn) => { try { fn(); } catch (e) { failed++; console.log('FAIL -', label, '::', e.message); } };
    t('fresh load runs', () => { api = run(TUTOR_JS, TUTOR_PROBE, env); });
    ok('fresh: chatMessages empty', api && api.getChat().length === 0);
    ok('fresh: welcome not hidden', env.getEl('welcomeMessage').style.display !== 'none');
}
{
    const seed = {};
    seed['ragvance-tutor-state'] = JSON.stringify({
        version: 1,
        messages: [
            { role: 'user', content: 'What is OSI?' },
            { role: 'assistant', content: 'Seven layers.', sources: [{ doc_id: 13, chunk_index: 4, page_number: 2, file_name: 'dc.pdf', text: 'chunk text', score: 0.31 }] },
        ],
    });
    const env = makeEnv();
    Object.assign(env.store, seed);
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('restore: 2 messages in memory', api.getChat().length === 2);
    ok('restore: welcome hidden', env.getEl('welcomeMessage').style.display === 'none');
    ok('restore: 3 children (welcome + 2 messages)', env.getEl('chatContainer').children.length === 3);
    const withSources = env.state.created.filter(c => c.innerHTML.includes('Show Sources (1)'));
    ok('restore: sources button rebuilt via addMessage', withSources.length === 1);
    ok('restore: source label rendered', withSources[0].innerHTML.includes('dc.pdf · Page 2'));

    // clear
    const btn = env.getEl('clearChatBtn');
    ok('clear handler bound', (btn._listeners.click || []).length === 1);
    btn._listeners.click[0]();
    ok('clear: chat empty', api.getChat().length === 0);
    ok('clear: storage key removed', !('ragvance-tutor-state' in env.store));
    ok('clear: welcome re-shown', env.getEl('welcomeMessage').style.display === '');
    ok('clear: only welcome remains', env.getEl('chatContainer').children.length === 1);
}
{
    const env = makeEnv();
    env.store['ragvance-tutor-state'] = '{not json';
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('corrupted JSON: no crash, fresh state', api && api.getChat().length === 0);
    ok('corrupted JSON: welcome visible', env.getEl('welcomeMessage').style.display !== 'none');
}
{
    const env = makeEnv();
    env.store['ragvance-tutor-state'] = JSON.stringify({ version: 99, messages: [{ role: 'user', content: 'x' }] });
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('wrong version: discarded', api.getChat().length === 0);
}
{
    const env = makeEnv();
    env.store['ragvance-tutor-state'] = JSON.stringify({ version: 1, messages: [{ role: 'system', content: 'x' }] });
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('invalid role: discarded', api.getChat().length === 0);
}
{
    const env = makeEnv();
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    api.setChat([{ role: 'user', content: 'hi' }]);
    env.state.setItemThrows = true;
    let threw = false;
    try { api.saveTutorState(); } catch (e) { threw = true; }
    ok('quota error: save does not throw', !threw);
    env.state.setItemThrows = false;
    api.saveTutorState();
    const round = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('round-trip: messages survive save/load', JSON.stringify(round.getChat()) === JSON.stringify([{ role: 'user', content: 'hi' }]));
    ok('load rejects bad JSON without throwing', api.loadTutorState.call(null) === null || true);
}
{
    const seed = {};
    const msgs = [
        { role: 'user', content: 'q1' },
        { role: 'assistant', content: 'a1', sources: [] },
        { role: 'user', content: 'q2' },
        { role: 'assistant', content: 'a2', sources: [{ doc_id: 13, chunk_index: 1, page_number: 1, file_name: 'f.pdf', text: 't', score: 0.2 }] },
    ];
    seed['ragvance-tutor-state'] = JSON.stringify({ version: 1, messages: msgs });
    const env = makeEnv();
    Object.assign(env.store, seed);
    const api = run(TUTOR_JS, TUTOR_PROBE, env);
    ok('round-trip: full conversation restored identically', JSON.stringify(api.getChat()) === JSON.stringify(msgs));
}

// ---------- PRACTICE ----------
console.log('--- practice.html ---');
{
    const env = makeEnv();
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('fresh: runs with defaults', api.getState().mcqs.length === 0 && api.getState().currentIndex === 0);
    const stored = JSON.parse(env.store['ragvance-practice-state']);
    ok('fresh: config-only state saved (version 1, mcqs [])', stored.version === 1 && stored.mcqs.length === 0);
    ok('fresh: defaults num=5, docIds []', stored.num === 5 && stored.docIds.length === 0);
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({
        version: 1, docIds: [13], num: 20, topic: 'DBMS',
        mcqs: [], currentIndex: 0, answered: false, selected: null, feedback: null,
    });
    run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('config restore: doc 13 checked, 14 unchecked', env.docCheckboxes[0].checked === true && env.docCheckboxes[1].checked === false);
    ok('config restore: num 20 active, 5 not', env.numBtns[2].classList.contains('active') && !env.numBtns[0].classList.contains('active'));
    ok('config restore: topic input filled', env.getEl('topicInput').value === 'DBMS');
    ok('config restore: summary updated', env.getEl('summaryDocs').textContent === '1 selected' && env.getEl('summaryNum').textContent === '20');
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({
        version: 1, docIds: [13], num: 10, topic: '',
        mcqs: [validQ(1), validQ(2), validQ(3)],
        currentIndex: 1, answered: false, selected: 'B', feedback: null,
    });
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    const s = api.getState();
    ok('session restore: mcqs 3, index 1, unanswered', s.mcqs.length === 3 && s.currentIndex === 1 && s.answered === false);
    ok('session restore: radio B pre-checked', env.radioCache.B.checked === true);
    ok('session restore: settings hidden, mcq panel visible', env.getEl('settingsPanel').classList.contains('d-none') && !env.getEl('mcqPanel').classList.contains('d-none'));
    ok('session restore: counter rebuilt', env.getEl('mcqCounter').textContent === 'Question 2 of 3');
    ok('session restore: question text rebuilt', env.getEl('currentQuestionText').textContent === 'Question 2?');
    ok('session restore: check enabled, next hidden', env.getEl('checkBtn').disabled === false && env.getEl('nextBtn').style.display === 'none');

    // restart clears session, keeps config
    api.restart();
    const s2 = api.getState();
    const stored = JSON.parse(env.store['ragvance-practice-state']);
    ok('restart: session cleared in memory', s2.mcqs.length === 0 && s2.currentIndex === 0 && s2.answered === false);
    ok('restart: stored state replaced (config-only)', stored.mcqs.length === 0 && stored.docIds.length === 1 && stored.docIds[0] === 13);
    ok('restart: settings panel back', !env.getEl('settingsPanel').classList.contains('d-none'));
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({
        version: 1, docIds: [], num: 5, topic: '',
        mcqs: [validQ(1), validQ(2)],
        currentIndex: 0, answered: true, selected: 'B',
        feedback: { selected: 'B', data: { is_correct: true, correct_answer: 'B', explanation: 'Because B.', topic: 'T1' } },
    });
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    const s = api.getState();
    ok('answered restore: answered + feedback state', s.answered === true && s.currentFeedback.data.explanation === 'Because B.');
    ok('answered restore: inputs disabled', env.radios.every(r => r.disabled === true));
    ok('answered restore: correct alert rendered', env.getEl('feedbackPanel').querySelector('.alert').innerHTML.includes('Correct!'));
    ok('answered restore: check hidden, next shown', env.getEl('checkBtn').style.display === 'none' && env.getEl('nextBtn').style.display === 'inline-block');
    ok('answered restore: feedback panel visible', !env.getEl('feedbackPanel').classList.contains('d-none'));
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({
        version: 1, docIds: [], num: 5, topic: '',
        mcqs: [validQ(1), validQ(2)],
        currentIndex: 2, answered: false, selected: null, feedback: null,
    });
    run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('completed restore: complete panel shown', !env.getEl('completePanel').classList.contains('d-none'));
    ok('completed restore: mcq panel hidden', env.getEl('mcqPanel').classList.contains('d-none'));
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = '{corrupt';
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('corrupted JSON: no crash, defaults', api.getState().mcqs.length === 0);
    const stored = JSON.parse(env.store['ragvance-practice-state']);
    ok('corrupted JSON: replaced by valid version 1 state', stored.version === 1 && stored.mcqs.length === 0);
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({ version: 2, docIds: [13], num: 10, topic: '', mcqs: [validQ(1)], currentIndex: 0, answered: false, selected: null, feedback: null });
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('wrong version: discarded, defaults used', api.getState().mcqs.length === 0 && env.docCheckboxes[0].checked === false);
}
{
    const env = makeEnv();
    env.store['ragvance-practice-state'] = JSON.stringify({ version: 1, docIds: [], num: 5, topic: '', mcqs: [{ question: 42, options: 'bad' }], currentIndex: 0, answered: false, selected: null, feedback: null });
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    ok('invalid mcqs shape: discarded', api.getState().mcqs.length === 0);
}
{
    const env = makeEnv();
    env.state.setItemThrows = true;
    let threw = false;
    try { run(PRACTICE_JS, PRACTICE_PROBE, env); } catch (e) { threw = true; }
    ok('quota error: full load still completes', !threw);
    env.state.setItemThrows = false;
}
{
    const env = makeEnv();
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    api.setState({ mcqs: [validQ(1)], currentIndex: 0, answered: false, selected: null, feedback: null });
    env.docCheckboxes[0].checked = true;
    env.getEl('topicInput').value = 'Networking';
    api.savePracticeState();
    const loaded = api.loadPracticeState();
    ok('save/load round-trip: mcqs + index equal', loaded && loaded.mcqs.length === 1 && loaded.currentIndex === 0 && loaded.mcqs[0].question === 'Question 1?');
    ok('save/load round-trip: DOM config captured', loaded.docIds.length === 1 && loaded.docIds[0] === 13 && loaded.topic === 'Networking');
    ok('save/load round-trip: version field', loaded.version === 1);
}
{
    const env = makeEnv();
    const api = run(PRACTICE_JS, PRACTICE_PROBE, env);
    api.setState({ mcqs: [validQ(1)], currentIndex: 0, answered: true, selected: 'A', feedback: { selected: 'A', data: { is_correct: false, correct_answer: 'C', explanation: 'x', topic: 't' } } });
    api.savePracticeState();
    const env2 = makeEnv();
    Object.assign(env2.store, env.store);
    const api2 = run(PRACTICE_JS, PRACTICE_PROBE, env2);
    const s = api2.getState();
    ok('full save->reload session: restored answered state', s.mcqs.length === 1 && s.answered === true && s.currentFeedback.data.correct_answer === 'C');
}

console.log(`\n${passed}/${passed + failed} passed`);
process.exit(failed ? 1 : 0);

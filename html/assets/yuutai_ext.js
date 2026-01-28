(() => {
    'use strict';

    const SETTINGS_DEFAULT = {
        kInst: 0.8,
        kGen: 1.0,
        extraDays: 30,
        borrowAPR: 1.7,
        taxAdj: 0.0,
        stepYen: 1000
    };

    const STORAGE_KEYS = {
        kInst: 'yuutai_setting_k_inst',
        kGen: 'yuutai_setting_k_gen',
        extraDays: 'yuutai_setting_extra_days',
        borrowAPR: 'yuutai_setting_borrow_apr',
        taxAdj: 'yuutai_setting_tax_adj',
        stepYen: 'yuutai_setting_step_yen'
    };

    const UI_STATE_KEYS = {
        focusCurrentOnly: 'yuutaiext_focus_current_only',
        openPortfolio: 'yuutaiext_open_portfolio',
        openFilter: 'yuutaiext_open_filter',
        openSettings: 'yuutaiext_open_settings',
        odeltaOpen: 'yuutaiext_odelta_open',
        openEarly: 'yuutaiext_open_early',
        openScenario: 'yuutaiext_open_scenario'
    };

    const state = {
        settings: { ...SETTINGS_DEFAULT },
        monthCache: new Map(),
        curveCache: new Map(),
        monthCurveCache: new Map(),
        debounceTimer: null,
        lastVisibleKey: ''
    };

    const portfolioCard = document.querySelector('.portfolio-card');
    if (!portfolioCard) {
        return;
    }

    const availableCapitalInput = document.getElementById('available-capital');

    const extElements = {
        settingsCard: null,
        curveCard: null,
        earlyCard: null,
        scenarioCard: null,
        targetSelect: null,
        deltaInput: null,
        deltaRange: null,
        deltaSetBtn: null,
        nikkoToggle: null,
        requiredSpreadValue: null,
        curveBody: null,
        earlyBody: null,
        scenarioBody: null,
        warningBox: null,
        settingsValue: {}
    };

    const formatNumber = (num) => {
        if (!Number.isFinite(num)) return '0';
        return Math.round(num).toLocaleString('ja-JP');
    };

    const formatYen = (num) => {
        if (!Number.isFinite(num)) return '—';
        return Math.round(num).toLocaleString('ja-JP');
    };

    const formatManYen = (amountYen) => {
        if (!Number.isFinite(amountYen)) return '—';
        const man = amountYen / 10000;
        if (!Number.isFinite(man)) return '—';
        const s = man >= 1000 ? formatNumber(man) : man.toFixed(1).replace(/\.0$/, '');
        return `${s}万`;
    };

    const amountCellHtml = (amountYen) => {
        if (!Number.isFinite(amountYen) || amountYen <= 0) {
            return '<td class="yuutai-ext__amt">—</td>';
        }
        const yenStr = formatYen(amountYen);
        const manStr = formatManYen(amountYen);
        return `<td class="yuutai-ext__amt" title="${yenStr}円"><div class="yuutai-ext__amt-man">${manStr}</div><div class="yuutai-ext__amt-yen">${yenStr}円</div></td>`;
    };

    const parseNumber = (value) => {
        if (value == null) return 0;
        const str = String(value).replace(/,/g, '').replace(/[^\d.-]/g, '');
        const parsed = parseFloat(str);
        return Number.isFinite(parsed) ? parsed : 0;
    };

    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

    const getAvailableCapital = () => {
        if (!availableCapitalInput) return 0;
        return Math.max(0, Math.floor(parseNumber(availableCapitalInput.value)));
    };

    const getSelectedTotal = () => {
        let total = 0;
        document.querySelectorAll('.stock-checkbox:checked').forEach((cb) => {
            const row = cb.closest('tr');
            if (!row) return;
            total += parseNumber(row.dataset.amount || 0);
        });
        return total;
    };

    const readSettings = () => {
        const load = (key, fallback) => {
            const raw = localStorage.getItem(key);
            if (raw == null) return fallback;
            const num = parseFloat(raw);
            return Number.isFinite(num) ? num : fallback;
        };

        state.settings = {
            kInst: clamp(load(STORAGE_KEYS.kInst, SETTINGS_DEFAULT.kInst), 0.6, 1.0),
            kGen: clamp(load(STORAGE_KEYS.kGen, SETTINGS_DEFAULT.kGen), 0.6, 1.0),
            extraDays: clamp(Math.round(load(STORAGE_KEYS.extraDays, SETTINGS_DEFAULT.extraDays)), 0, 365),
            borrowAPR: clamp(load(STORAGE_KEYS.borrowAPR, SETTINGS_DEFAULT.borrowAPR), 0, 20),
            taxAdj: clamp(load(STORAGE_KEYS.taxAdj, SETTINGS_DEFAULT.taxAdj), -0.5, 0.5),
            stepYen: clamp(Math.round(load(STORAGE_KEYS.stepYen, SETTINGS_DEFAULT.stepYen)), 100, 100000)
        };
    };

    const persistSetting = (key, value) => {
        localStorage.setItem(key, String(value));
    };

    const getStorageBool = (key, fallback) => {
        const raw = localStorage.getItem(key);
        if (raw == null) return fallback;
        return raw === '1';
    };

    const setStorageBool = (key, value) => {
        localStorage.setItem(key, value ? '1' : '0');
    };

    const ensureStorageBoolDefault = (key, defaultValue) => {
        const raw = localStorage.getItem(key);
        if (raw == null) {
            setStorageBool(key, defaultValue);
        }
    };

    const isFocusCurrentOnlyEnabled = () => getStorageBool(UI_STATE_KEYS.focusCurrentOnly, true);

    let suppressUiStatePersist = false;
    const collapsibles = [];

    const withSuppressPersist = (fn) => {
        suppressUiStatePersist = true;
        try {
            fn();
        } finally {
            suppressUiStatePersist = false;
        }
    };

    const bindPersistOnToggle = (detailsEl, storageKey) => {
        if (!detailsEl || !storageKey) return;
        detailsEl.addEventListener('toggle', () => {
            if (suppressUiStatePersist) return;
            if (isFocusCurrentOnlyEnabled()) return;
            setStorageBool(storageKey, detailsEl.open);
        });
    };

    const registerCollapsible = (detailsEl, storageKey, defaultOpen) => {
        if (!detailsEl) return;
        if (detailsEl.dataset.yuutaiExtCollapsibleRegistered === '1') return;
        detailsEl.dataset.yuutaiExtCollapsibleRegistered = '1';
        collapsibles.push({ detailsEl, storageKey, defaultOpen });
        bindPersistOnToggle(detailsEl, storageKey);
    };

    const syncCollapsibleOpen = ({ detailsEl, storageKey, defaultOpen }) => {
        if (!detailsEl) return;
        const focusEnabled = isFocusCurrentOnlyEnabled();
        const shouldOpen = focusEnabled ? false : getStorageBool(storageKey, defaultOpen);
        withSuppressPersist(() => {
            detailsEl.open = shouldOpen;
        });
    };

    const syncAllCollapsibles = () => {
        collapsibles.forEach(syncCollapsibleOpen);
    };

    const injectFocusToggle = () => {
        if (document.getElementById('yuutai-ext-focus-toggle')) return;
        const target = document.querySelector('.page-header .header-content .interest-info')
            || document.querySelector('.page-header .header-content')
            || document.querySelector('.page-header');
        if (!target) return;

        const wrapper = document.createElement('div');
        wrapper.className = 'yuutai-ext-focus-toggle';
        wrapper.innerHTML = `
            <label class="yuutai-ext-focus-label">
                <input type="checkbox" id="yuutai-ext-focus-toggle">
                <span class="yuutai-ext-focus-switch" aria-hidden="true"></span>
                <span class="yuutai-ext-focus-text">フォーカス表示（当月の優待以外は閉じる）</span>
            </label>
        `;
        target.appendChild(wrapper);

        const checkbox = wrapper.querySelector('#yuutai-ext-focus-toggle');
        if (!checkbox) return;
        checkbox.checked = isFocusCurrentOnlyEnabled();
        checkbox.addEventListener('change', () => {
            setStorageBool(UI_STATE_KEYS.focusCurrentOnly, checkbox.checked);
            syncAllCollapsibles();
        });
    };

    const makeHostCollapsible = (hostEl, { title, headerSelector, storageKey, defaultOpen = true, detailsClass = '', bodyClass = '' }) => {
        if (!hostEl) return null;
        const existingDetails = Array.from(hostEl.children).find((child) => (
            child.tagName === 'DETAILS' && child.classList.contains('yuutai-ext-section-collapsible')
        ));
        if (existingDetails) return existingDetails;

        let headerEl = null;
        if (headerSelector) {
            const normalized = headerSelector.replace(/^:scope\s*>\s*/, '');
            const candidate = hostEl.querySelector(normalized);
            headerEl = candidate && candidate.parentElement === hostEl ? candidate : null;
        }

        const details = document.createElement('details');
        details.className = ['yuutai-ext-section-collapsible', 'yuutai-ext-collapsible', detailsClass].filter(Boolean).join(' ');

        const summary = document.createElement('summary');
        summary.className = 'yuutai-ext-collapsible-summary';

        if (headerEl) {
            headerEl.remove();
            summary.appendChild(headerEl);
        } else {
            const h2 = document.createElement('h2');
            h2.textContent = title || '';
            summary.appendChild(h2);
        }

        const chevron = document.createElement('span');
        chevron.className = 'yuutai-ext-collapsible-chevron';
        chevron.setAttribute('aria-hidden', 'true');
        summary.appendChild(chevron);

        const body = document.createElement('div');
        body.className = ['yuutai-ext-collapsible-body', bodyClass].filter(Boolean).join(' ');
        while (hostEl.firstChild) {
            body.appendChild(hostEl.firstChild);
        }

        details.appendChild(summary);
        details.appendChild(body);
        hostEl.appendChild(details);

        registerCollapsible(details, storageKey, defaultOpen);
        syncCollapsibleOpen({ detailsEl: details, storageKey, defaultOpen });
        return details;
    };

    const getVisibleRows = () => {
        return Array.from(document.querySelectorAll('tbody tr')).filter((row) => row.style.display !== 'none');
    };

    const extractRowData = (row) => {
        const amount = parseNumber(row.dataset.amount || 0);
        const instBasePct = parseFloat(row.dataset.performance || '0');
        const genBaseRaw = row.dataset.monthlyYield;
        const genBasePct = genBaseRaw == null ? null : parseFloat(genBaseRaw);
        const stockKey = row.dataset.stockKey || '';
        const codeCell = row.querySelector('td:nth-child(2) a') || row.querySelector('td a');
        const code = (stockKey.split('_')[0] || (codeCell ? codeCell.textContent : '') || '').trim();
        const nameCell = row.querySelector('.name-cell a') || row.querySelector('.name-cell');
        const name = nameCell ? nameCell.textContent.trim() : '';
        const nikko = row.dataset.nikko === 'true';
        const checkbox = row.querySelector('.stock-checkbox');

        return {
            row,
            amount,
            instBasePct: Number.isFinite(instBasePct) ? instBasePct : 0,
            genBasePct: Number.isFinite(genBasePct) ? genBasePct : null,
            code,
            name,
            nikko,
            checkbox,
            key: stockKey || code
        };
    };

    const computeExpected = (data, settings) => {
        const instExpectedPct = data.instBasePct * settings.kInst + settings.taxAdj;
        const genExpectedPct = data.genBasePct == null ? null : data.genBasePct * settings.kGen + settings.taxAdj;
        return { instExpectedPct, genExpectedPct };
    };

    const buildItemsForDP = (rowsData, settings, unit) => {
        const items = [];
        rowsData.forEach((data) => {
            const { instExpectedPct } = computeExpected(data, settings);
            if (!Number.isFinite(instExpectedPct) || instExpectedPct <= 0) return;
            if (!Number.isFinite(data.amount) || data.amount <= 0) return;
            const w = Math.floor(data.amount / unit);
            if (w <= 0) return;
            const v = data.amount * instExpectedPct / 100;
            items.push({
                key: data.key,
                code: data.code,
                name: data.name,
                amount: data.amount,
                instExpectedPct,
                w,
                v,
                checkbox: data.checkbox
            });
        });
        return items;
    };

    const dpSolve = (items, capacityYen, unit, withChoice) => {
        const W = Math.floor(capacityYen / unit);
        if (W <= 0) {
            return { dp: new Float64Array(Math.max(1, W + 1)), W, unit, choose: null, prev: null };
        }
        const dp = new Float64Array(W + 1);
        const choose = withChoice ? new Int32Array(W + 1).fill(-1) : null;
        const prev = withChoice ? new Int32Array(W + 1).fill(-1) : null;

        for (let i = 0; i < items.length; i++) {
            const w = items[i].w;
            const v = items[i].v;
            for (let cap = W; cap >= w; cap--) {
                const candidate = dp[cap - w] + v;
                if (candidate > dp[cap] + 1e-9) {
                    dp[cap] = candidate;
                    if (withChoice) {
                        choose[cap] = i;
                        prev[cap] = cap - w;
                    }
                }
            }
        }

        return { dp, W, unit, choose, prev };
    };

    const buildCurveKey = (items, capacityYen, unit, tag) => {
        const parts = items.map((item) => `${item.key}:${item.amount}:${item.instExpectedPct.toFixed(4)}`);
        return `${tag}|${capacityYen}|${unit}|${parts.join('|')}`;
    };

    const getCurve = (items, capacityYen, unit, tag, cacheMap) => {
        const key = buildCurveKey(items, capacityYen, unit, tag);
        if (cacheMap.has(key)) {
            return cacheMap.get(key);
        }
        const result = dpSolve(items, capacityYen, unit, false);
        cacheMap.set(key, result);
        return result;
    };

    const getMarginalPct = (curve, capacityYen, deltaYen) => {
        if (!curve || curve.W <= 0) return 0;
        if (deltaYen <= 0) return 0;
        const unit = curve.unit;
        const cappedDelta = Math.min(deltaYen, capacityYen);
        const reducedCap = Math.max(0, capacityYen - cappedDelta);
        const wReduced = Math.floor(reducedCap / unit);
        const loss = curve.dp[curve.W] - curve.dp[wReduced];
        return loss / cappedDelta * 100;
    };

    const renderSettingsValues = () => {
        extElements.settingsValue.kInst.textContent = state.settings.kInst.toFixed(2);
        extElements.settingsValue.kGen.textContent = state.settings.kGen.toFixed(2);
        extElements.settingsValue.extraDays.textContent = `${state.settings.extraDays}日`;
        extElements.settingsValue.borrowAPR.textContent = `${state.settings.borrowAPR.toFixed(2)}%`;
        extElements.settingsValue.taxAdj.textContent = `${state.settings.taxAdj.toFixed(2)}%`;
        extElements.settingsValue.stepYen.textContent = `${formatNumber(state.settings.stepYen)}円`;
    };

    const debounceUpdate = () => {
        if (state.debounceTimer) {
            clearTimeout(state.debounceTimer);
        }
        state.debounceTimer = setTimeout(() => {
            updateAll();
        }, 200);
    };

    const updateCurveCard = () => {
        if (!extElements.curveBody) return;
        const capacityYen = getAvailableCapital();
        const rows = getVisibleRows();
        if (capacityYen <= 0) {
            extElements.curveBody.innerHTML = '<div class="yuutai-ext-warning">利用可能資金を入力するとO(δ)が計算されます。</div>';
            return null;
        }
        const unit = Math.max(100, state.settings.stepYen);
        const items = buildItemsForDP(rows.map(extractRowData), state.settings, unit);
        if (items.length === 0) {
            extElements.curveBody.innerHTML = '<div class="yuutai-ext-warning">利回りが正の銘柄がありません。</div>';
            return null;
        }
        const W = Math.floor(capacityYen / unit);
        if (W > 200000) {
            extElements.curveBody.innerHTML = '<div class="yuutai-ext-warning">DP刻みが細かすぎて計算が重くなるため、刻みを大きくしてください。</div>';
            return null;
        }

        const curve = getCurve(items, capacityYen, unit, 'current', state.curveCache);
        const maxDelta = Math.min(3000000, capacityYen);
        const step = 100000;
        let html = '<table class="yuutai-ext-table"><thead><tr><th>δ(万円)</th><th>lost(円)</th><th>O(δ)%</th><th>100万円あたり(円)</th></tr></thead><tbody>';
        for (let delta = 0; delta <= maxDelta; delta += step) {
            const oPct = delta === 0 ? 0 : getMarginalPct(curve, capacityYen, delta);
            const loss = delta === 0 ? 0 : oPct / 100 * delta;
            const perMillion = oPct * 10000;
            html += `<tr><td>${(delta / 10000).toFixed(0)}</td><td>${formatNumber(loss)}</td><td>${oPct.toFixed(2)}</td><td>${formatNumber(perMillion)}</td></tr>`;
        }
        html += '</tbody></table>';
        extElements.curveBody.innerHTML = html;
        return curve;
    };

    const fetchMonthHtml = async (month) => {
        if (state.monthCache.has(month)) {
            return state.monthCache.get(month);
        }
        const result = { ok: false, rows: [], error: null };
        try {
            const res = await fetch(`../months/${month}.html`, { cache: 'no-store' });
            if (!res.ok) {
                result.error = `HTTP ${res.status}`;
                state.monthCache.set(month, result);
                return result;
            }
            const text = await res.text();
            const doc = new DOMParser().parseFromString(text, 'text/html');
            const rows = Array.from(doc.querySelectorAll('tbody tr')).map((row) => {
                const data = extractRowData(row);
                return data;
            }).filter((data) => Number.isFinite(data.amount) && data.amount > 0);
            result.ok = true;
            result.rows = rows;
            state.monthCache.set(month, result);
            return result;
        } catch (err) {
            result.error = err instanceof Error ? err.message : 'fetch failed';
            state.monthCache.set(month, result);
            return result;
        }
    };

    const computeMonthCurve = async (month, capacityYen, unit, settings) => {
        const cacheKey = `${month}|${capacityYen}|${unit}|${settings.kInst}|${settings.taxAdj}`;
        if (state.monthCurveCache.has(cacheKey)) {
            return state.monthCurveCache.get(cacheKey);
        }
        const data = await fetchMonthHtml(month);
        if (!data.ok) {
            return { ok: false, error: data.error };
        }
        const items = buildItemsForDP(data.rows, settings, unit);
        const W = Math.floor(capacityYen / unit);
        if (W > 200000) {
            return { ok: false, error: 'DP too large' };
        }
        const curve = dpSolve(items, capacityYen, unit, false);
        const result = { ok: true, curve };
        state.monthCurveCache.set(cacheKey, result);
        return result;
    };

    const computeCurrentCurve = (settings) => {
        const capacityYen = getAvailableCapital();
        const unit = Math.max(100, settings.stepYen);
        const rows = getVisibleRows();
        const items = buildItemsForDP(rows.map(extractRowData), settings, unit);
        const W = Math.floor(capacityYen / unit);
        if (capacityYen <= 0 || items.length === 0 || W > 200000) {
            return null;
        }
        return dpSolve(items, capacityYen, unit, false);
    };

    const computeEarlySimulation = async () => {
        if (!extElements.earlyBody) return;
        const capacityYen = getAvailableCapital();
        if (capacityYen <= 0) {
            extElements.earlyBody.innerHTML = '<div class="yuutai-ext-warning">利用可能資金を入力すると早期取得の判定ができます。</div>';
            return;
        }
        const currentCurve = updateCurveCard();
        if (!currentCurve) {
            extElements.earlyBody.innerHTML = '<div class="yuutai-ext-warning">O(δ) が計算できません。</div>';
            return;
        }

        const targetMonth = extElements.targetSelect.value;
        const deltaYen = parseNumber(extElements.deltaInput.value) * 10000;
        const nikkoOnly = extElements.nikkoToggle.checked;

        const currentMonth = getCurrentMonth();
        const nextMonth = getNextMonth(currentMonth, 1);
        const nextNextMonth = getNextMonth(currentMonth, 2);

        const earlyCostPct = state.settings.borrowAPR * (state.settings.extraDays / 365);
        let opportunityCostPct = getMarginalPct(currentCurve, capacityYen, deltaYen);

        if (targetMonth === nextNextMonth) {
            const unit = Math.max(100, state.settings.stepYen);
            const nextCurveResult = await computeMonthCurve(nextMonth, capacityYen, unit, state.settings);
            if (!nextCurveResult.ok) {
                extElements.earlyBody.innerHTML = '<div class="yuutai-ext-warning">翌月データの読み込みに失敗しました。ローカルファイル直開きの場合は簡易HTTPサーバで開いてください。</div>';
                return;
            }
            opportunityCostPct += getMarginalPct(nextCurveResult.curve, capacityYen, deltaYen);
        }

        const targetData = await fetchMonthHtml(targetMonth);
        if (!targetData.ok) {
            extElements.earlyBody.innerHTML = '<div class="yuutai-ext-warning">他月データの読み込みに失敗しました。ローカルファイル直開きの場合は簡易HTTPサーバで開いてください。</div>';
            return;
        }

        const requiredSpreadPct = opportunityCostPct + earlyCostPct;
        extElements.requiredSpreadValue.textContent = `${requiredSpreadPct.toFixed(2)}%`;

        let items = targetData.rows.map((row) => {
            const expected = computeExpected(row, state.settings);
            const spreadPct = expected.genExpectedPct == null ? null : expected.genExpectedPct - expected.instExpectedPct;
            const marginPct = spreadPct == null ? null : spreadPct - requiredSpreadPct;
            return {
                code: row.code,
                name: row.name,
                amount: row.amount,
                nikko: row.nikko,
                instExpectedPct: expected.instExpectedPct,
                genExpectedPct: expected.genExpectedPct,
                spreadPct,
                marginPct
            };
        }).filter((item) => item.spreadPct != null);

        if (nikkoOnly) {
            items = items.filter((item) => item.nikko);
        }

        items.sort((a, b) => (b.marginPct ?? -999) - (a.marginPct ?? -999));

        const colSpan = 10;
        let html = '<table class="yuutai-ext-table"><thead><tr><th>コード</th><th class="yuutai-ext__name">銘柄</th><th>取得金額</th><th>日興</th><th>gen%</th><th>inst%</th><th>spread%</th><th>必要%</th><th>margin%</th><th>判定</th></tr></thead><tbody>';
        if (!items.length) {
            html += `<tr><td colspan="${colSpan}">候補がありません（フィルタ/日興在庫トグルをご確認ください）</td></tr>`;
        }
        items.forEach((item) => {
            const ok = item.marginPct >= 0;
            const amtTag =
                Number.isFinite(item.amount) && item.amount > 0
                    ? `<span class="yuutai-ext__amt-tag">${formatManYen(item.amount)}</span>`
                    : '';
            html += `<tr><td>${item.code}</td><td class="yuutai-ext__name" title="${item.name}">${amtTag}${item.name}</td>${amountCellHtml(item.amount)}<td>${item.nikko ? 'あり' : 'なし'}</td><td>${item.genExpectedPct.toFixed(2)}</td><td>${item.instExpectedPct.toFixed(2)}</td><td>${item.spreadPct.toFixed(2)}</td><td>${requiredSpreadPct.toFixed(2)}</td><td>${item.marginPct.toFixed(2)}</td><td><span class="yuutai-ext-badge ${ok ? 'ok' : 'ng'}">${ok ? 'OK' : 'NG'}</span></td></tr>`;
        });
        html += '</tbody></table>';
        extElements.earlyBody.innerHTML = html;

        await updateScenarioComparison(targetMonth, deltaYen, nikkoOnly, earlyCostPct, capacityYen);
    };

    const updateScenarioComparison = async (targetMonth, deltaYen, nikkoOnly, earlyCostPct, capacityYen) => {
        if (!extElements.scenarioBody) return;
        const currentMonth = getCurrentMonth();
        const nextMonth = getNextMonth(currentMonth, 1);
        const nextNextMonth = getNextMonth(currentMonth, 2);
        const scenarioKs = [0.7, 0.8, 0.9, 1.0];

        const targetData = await fetchMonthHtml(targetMonth);
        if (!targetData.ok) {
            extElements.scenarioBody.innerHTML = '<div class="yuutai-ext-warning">他月データの読み込みに失敗しました。</div>';
            return;
        }

        let html = '<table class="yuutai-ext-table"><thead><tr><th>K_inst</th><th>必要%</th><th>OK件数</th><th>最小OK margin</th><th>上位3コード</th></tr></thead><tbody>';

        for (const kInst of scenarioKs) {
            const settings = { ...state.settings, kInst };
            let oppCostPct = 0;
            if (targetMonth === nextNextMonth) {
                const unit = Math.max(100, settings.stepYen);
                const nextCurveResult = await computeMonthCurve(nextMonth, capacityYen, unit, settings);
                if (!nextCurveResult.ok) {
                    html += `<tr><td>${kInst.toFixed(2)}</td><td>--</td><td>--</td><td>読み込み失敗</td></tr>`;
                    continue;
                }
                const currentCurve = computeCurrentCurve(settings);
                if (!currentCurve) {
                    html += `<tr><td>${kInst.toFixed(2)}</td><td>--</td><td>--</td><td>曲線未計算</td></tr>`;
                    continue;
                }
                oppCostPct = getMarginalPct(currentCurve, capacityYen, deltaYen) + getMarginalPct(nextCurveResult.curve, capacityYen, deltaYen);
            } else {
                const currentCurve = computeCurrentCurve(settings);
                if (!currentCurve) {
                    html += `<tr><td>${kInst.toFixed(2)}</td><td>--</td><td>--</td><td>曲線未計算</td></tr>`;
                    continue;
                }
                oppCostPct = getMarginalPct(currentCurve, capacityYen, deltaYen);
            }

            const requiredSpreadPct = oppCostPct + earlyCostPct;
            let items = targetData.rows.map((row) => {
                const expected = computeExpected(row, settings);
                const spreadPct = expected.genExpectedPct == null ? null : expected.genExpectedPct - expected.instExpectedPct;
                const marginPct = spreadPct == null ? null : spreadPct - requiredSpreadPct;
                return {
                    code: row.code,
                    nikko: row.nikko,
                    marginPct
                };
            }).filter((item) => item.marginPct != null);

            if (nikkoOnly) {
                items = items.filter((item) => item.nikko);
            }

            const okItems = items.filter((item) => item.marginPct >= 0);
            const okCount = okItems.length;
            const minOkMargin = okCount ? okItems.reduce((min, item) => Math.min(min, item.marginPct), Infinity) : null;
            items.sort((a, b) => b.marginPct - a.marginPct);
            const topCodes = items.slice(0, 3).map((item) => item.code).join(', ') || '--';

            html += `<tr><td>${kInst.toFixed(2)}</td><td>${requiredSpreadPct.toFixed(2)}</td><td>${okCount}</td><td>${minOkMargin == null ? '--' : minOkMargin.toFixed(2)}</td><td>${topCodes}</td></tr>`;
        }

        html += '</tbody></table>';
        extElements.scenarioBody.innerHTML = html;
    };

    const setupSettingsCard = () => {
        const card = document.createElement('div');
        card.className = 'glass-card yuutai-ext-card';
        card.innerHTML = `
            <div class="portfolio-header">
                <h2>拡張設定</h2>
            </div>
            <div class="yuutai-ext-grid">
                <div class="yuutai-ext-field">
                    <label>K_inst（制度の実現係数）</label>
                    <div class="yuutai-ext-control">
                        <input type="range" min="0.6" max="1" step="0.01" data-setting="kInst">
                        <span class="yuutai-ext-value" data-value="kInst"></span>
                    </div>
                </div>
                <div class="yuutai-ext-field">
                    <label>K_gen（一般/日興の実現係数）</label>
                    <div class="yuutai-ext-control">
                        <input type="range" min="0.6" max="1" step="0.01" data-setting="kGen">
                        <span class="yuutai-ext-value" data-value="kGen"></span>
                    </div>
                </div>
                <div class="yuutai-ext-field">
                    <label>extraDays（早取り追加ロック日数）</label>
                    <div class="yuutai-ext-control">
                        <input type="number" min="0" max="365" step="1" data-setting="extraDays">
                        <span class="yuutai-ext-value" data-value="extraDays"></span>
                    </div>
                    <div class="yuutai-ext-quick">
                        <button type="button" data-quick-days="7">7日</button>
                        <button type="button" data-quick-days="14">14日</button>
                        <button type="button" data-quick-days="30">30日</button>
                        <button type="button" data-quick-days="45">45日</button>
                    </div>
                </div>
                <div class="yuutai-ext-field">
                    <label>borrowAPR（一般信用金利 年率%）</label>
                    <div class="yuutai-ext-control">
                        <input type="number" min="0" max="20" step="0.01" data-setting="borrowAPR">
                        <span class="yuutai-ext-value" data-value="borrowAPR"></span>
                    </div>
                </div>
                <div class="yuutai-ext-field">
                    <label>taxAdj（税務/配当影響の補正 %ポイント）</label>
                    <div class="yuutai-ext-control">
                        <input type="range" min="-0.5" max="0.5" step="0.01" data-setting="taxAdj">
                        <span class="yuutai-ext-value" data-value="taxAdj"></span>
                    </div>
                    <div class="yuutai-ext-note">配当落調整金・税務差分などの不確実性をまとめて調整（固定しない）</div>
                </div>
                <div class="yuutai-ext-field">
                    <label>DP刻み（stepYen）</label>
                    <div class="yuutai-ext-control">
                        <input type="number" min="100" max="100000" step="100" data-setting="stepYen">
                        <span class="yuutai-ext-value" data-value="stepYen"></span>
                    </div>
                    <div class="yuutai-ext-note">精度↑ほど遅い</div>
                </div>
            </div>
        `;
        extElements.settingsCard = card;

        card.querySelectorAll('[data-value]').forEach((el) => {
            extElements.settingsValue[el.dataset.value] = el;
        });

        card.querySelectorAll('[data-setting]').forEach((input) => {
            const key = input.dataset.setting;
            input.addEventListener('input', () => {
                const value = parseNumber(input.value);
                state.settings[key] = value;
                persistSetting(STORAGE_KEYS[key], value);
                renderSettingsValues();
                debounceUpdate();
            });
            input.addEventListener('change', () => {
                const value = parseNumber(input.value);
                state.settings[key] = value;
                persistSetting(STORAGE_KEYS[key], value);
                renderSettingsValues();
                debounceUpdate();
            });
        });

        card.querySelectorAll('[data-quick-days]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const days = parseInt(btn.dataset.quickDays, 10);
                if (!Number.isFinite(days)) return;
                state.settings.extraDays = days;
                persistSetting(STORAGE_KEYS.extraDays, days);
                const input = card.querySelector('[data-setting="extraDays"]');
                if (input) input.value = days;
                renderSettingsValues();
                debounceUpdate();
            });
        });
    };

    const setupCurveCard = () => {
        const card = document.createElement('details');
        card.className = 'glass-card yuutai-ext-card yuutai-ext-collapsible';
        card.innerHTML = `
            <summary class="yuutai-ext-collapsible-summary">
                <h2>限界利回り（O(δ)）</h2>
                <span class="yuutai-ext-collapsible-chevron" aria-hidden="true"></span>
            </summary>
            <div class="yuutai-ext-body yuutai-ext-collapsible-body"></div>
        `;

        registerCollapsible(card, UI_STATE_KEYS.odeltaOpen, false);
        syncCollapsibleOpen({ detailsEl: card, storageKey: UI_STATE_KEYS.odeltaOpen, defaultOpen: false });

        extElements.curveCard = card;
        extElements.curveBody = card.querySelector('.yuutai-ext-body');
    };

    const setupEarlyCard = () => {
        const card = document.createElement('div');
        card.className = 'glass-card yuutai-ext-card';
        card.innerHTML = `
            <div class="portfolio-header">
                <h2>早期取得シミュレーション</h2>
            </div>
            <div class="yuutai-ext-inline">
                <label class="yuutai-ext-toggle">
                    対象月
                    <select data-role="targetMonth"></select>
                </label>
                <label class="yuutai-ext-toggle">
                    δ(万円)
                    <input type="number" data-role="deltaInput" min="0" step="10" value="100">
                </label>
                <input type="range" data-role="deltaRange" min="0" step="10" value="100">
                <button type="button" data-role="setDelta">選択中の必要資金をδにセット</button>
                <label class="yuutai-ext-toggle">
                    <input type="checkbox" data-role="nikkoOnly" checked>
                    日興在庫ありのみ
                </label>
            </div>
            <div class="yuutai-ext-inline" style="margin-top: 12px;">
                <div>必要スプレッド</div>
                <div class="yuutai-ext-emphasis" data-role="requiredSpread">--%</div>
            </div>
            <div class="yuutai-ext-body"></div>
        `;
        extElements.earlyCard = card;
        extElements.earlyBody = card.querySelector('.yuutai-ext-body');
        extElements.targetSelect = card.querySelector('[data-role="targetMonth"]');
        extElements.deltaInput = card.querySelector('[data-role="deltaInput"]');
        extElements.deltaRange = card.querySelector('[data-role="deltaRange"]');
        extElements.deltaSetBtn = card.querySelector('[data-role="setDelta"]');
        extElements.nikkoToggle = card.querySelector('[data-role="nikkoOnly"]');
        extElements.requiredSpreadValue = card.querySelector('[data-role="requiredSpread"]');

        extElements.deltaInput.addEventListener('input', () => {
            extElements.deltaRange.value = extElements.deltaInput.value;
            debounceUpdate();
        });

        extElements.deltaRange.addEventListener('input', () => {
            extElements.deltaInput.value = extElements.deltaRange.value;
            debounceUpdate();
        });

        extElements.deltaSetBtn.addEventListener('click', () => {
            const total = getSelectedTotal();
            const deltaMan = Math.round(total / 10000);
            extElements.deltaInput.value = deltaMan;
            extElements.deltaRange.value = deltaMan;
            debounceUpdate();
        });

        extElements.targetSelect.addEventListener('change', debounceUpdate);
        extElements.nikkoToggle.addEventListener('change', debounceUpdate);
    };

    const setupScenarioCard = () => {
        const card = document.createElement('div');
        card.className = 'glass-card yuutai-ext-card';
        card.innerHTML = `
            <div class="portfolio-header">
                <h2>Kシナリオ比較</h2>
            </div>
            <div class="yuutai-ext-body"></div>
        `;
        extElements.scenarioCard = card;
        extElements.scenarioBody = card.querySelector('.yuutai-ext-body');
    };

    const setupDpButton = () => {
        const autoBtn = document.getElementById('auto-select');
        if (!autoBtn) return;
        const dpBtn = document.createElement('button');
        dpBtn.type = 'button';
        dpBtn.className = 'auto-select-btn dp-select-btn';
        dpBtn.id = 'dp-select';
        dpBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 12h18"/>
                <path d="M12 3v18"/>
            </svg>
            最適（DP）
        `;
        autoBtn.insertAdjacentElement('afterend', dpBtn);

        dpBtn.addEventListener('click', () => {
            const capacityYen = getAvailableCapital();
            if (capacityYen <= 0) {
                alert('利用可能資金を入力してください');
                return;
            }
            const unit = Math.max(100, state.settings.stepYen);
            const rows = getVisibleRows();
            const items = buildItemsForDP(rows.map(extractRowData), state.settings, unit);
            if (items.length === 0) {
                alert('利回りが正の銘柄がありません');
                return;
            }
            const W = Math.floor(capacityYen / unit);
            if (W > 200000) {
                alert('DP刻みが細かすぎるため、刻みを大きくしてください');
                return;
            }

            const { dp, choose, prev } = dpSolve(items, capacityYen, unit, true);
            if (!choose || !prev) return;

            document.querySelectorAll('.stock-checkbox').forEach((cb) => {
                cb.checked = false;
            });

            let cap = dp.length - 1;
            const selectedKeys = new Set();
            while (cap >= 0 && choose[cap] >= 0) {
                const item = items[choose[cap]];
                selectedKeys.add(item.key);
                cap = prev[cap];
            }

            items.forEach((item) => {
                if (selectedKeys.has(item.key) && item.checkbox) {
                    item.checkbox.checked = true;
                }
            });

            if (typeof window.saveSelection === 'function') {
                window.saveSelection();
            }
            if (typeof window.calculatePortfolio === 'function') {
                window.calculatePortfolio();
            }
        });
    };

    const getCurrentMonth = () => {
        const match = window.location.pathname.match(/months\/(\d{2})\.html/);
        return match ? match[1] : '01';
    };

    const getNextMonth = (month, offset) => {
        const num = parseInt(month, 10);
        if (!Number.isFinite(num)) return '01';
        const next = ((num - 1 + offset) % 12) + 1;
        return String(next).padStart(2, '0');
    };

    const setupTargetOptions = () => {
        const currentMonth = getCurrentMonth();
        const nextMonth = getNextMonth(currentMonth, 1);
        const nextNextMonth = getNextMonth(currentMonth, 2);
        extElements.targetSelect.innerHTML = '';
        [nextMonth, nextNextMonth].forEach((month) => {
            const option = document.createElement('option');
            option.value = month;
            option.textContent = `${parseInt(month, 10)}月`;
            extElements.targetSelect.appendChild(option);
        });
    };

    const syncSettingsInputs = () => {
        const card = extElements.settingsCard;
        if (!card) return;
        const setValue = (key, value) => {
            const input = card.querySelector(`[data-setting="${key}"]`);
            if (input) input.value = value;
        };
        setValue('kInst', state.settings.kInst);
        setValue('kGen', state.settings.kGen);
        setValue('extraDays', state.settings.extraDays);
        setValue('borrowAPR', state.settings.borrowAPR);
        setValue('taxAdj', state.settings.taxAdj);
        setValue('stepYen', state.settings.stepYen);
        renderSettingsValues();
    };

    const syncDeltaLimits = () => {
        const capacityYen = getAvailableCapital();
        const maxDeltaMan = Math.floor(Math.min(3000000, capacityYen) / 10000);
        const current = clamp(parseNumber(extElements.deltaInput.value), 0, maxDeltaMan || 0);
        extElements.deltaInput.max = String(maxDeltaMan);
        extElements.deltaRange.max = String(maxDeltaMan);
        extElements.deltaInput.value = current;
        extElements.deltaRange.value = current;
    };

    const updateAll = async () => {
        syncDeltaLimits();
        updateCurveCard();
        await computeEarlySimulation();
    };

    const init = () => {
        ensureStorageBoolDefault(UI_STATE_KEYS.focusCurrentOnly, true);
        injectFocusToggle();

        readSettings();
        setupSettingsCard();
        setupCurveCard();
        setupEarlyCard();
        setupScenarioCard();
        setupDpButton();

        const fragment = document.createDocumentFragment();
        fragment.appendChild(extElements.settingsCard);
        fragment.appendChild(extElements.curveCard);
        fragment.appendChild(extElements.earlyCard);
        fragment.appendChild(extElements.scenarioCard);
        portfolioCard.parentNode.insertBefore(fragment, portfolioCard.nextSibling);

        makeHostCollapsible(portfolioCard, {
            title: 'ポートフォリオ計算',
            headerSelector: ':scope > .portfolio-header',
            storageKey: UI_STATE_KEYS.openPortfolio,
            defaultOpen: true,
            detailsClass: 'yuutai-ext-collapsible-host'
        });
        makeHostCollapsible(extElements.settingsCard, {
            title: '拡張設定',
            headerSelector: ':scope > .portfolio-header',
            storageKey: UI_STATE_KEYS.openSettings,
            defaultOpen: true,
            detailsClass: 'yuutai-ext-collapsible-host'
        });
        makeHostCollapsible(extElements.earlyCard, {
            title: '早期取得シミュレーション',
            headerSelector: ':scope > .portfolio-header',
            storageKey: UI_STATE_KEYS.openEarly,
            defaultOpen: true,
            detailsClass: 'yuutai-ext-collapsible-host'
        });
        makeHostCollapsible(extElements.scenarioCard, {
            title: 'Kシナリオ比較',
            headerSelector: ':scope > .portfolio-header',
            storageKey: UI_STATE_KEYS.openScenario,
            defaultOpen: true,
            detailsClass: 'yuutai-ext-collapsible-host'
        });

        const filterSection = document.querySelector('.filter-section');
        if (filterSection) {
            filterSection.classList.add('yuutai-ext-filter-collapsible-host');
            makeHostCollapsible(filterSection, {
                title: 'フィルタ',
                headerSelector: '',
                storageKey: UI_STATE_KEYS.openFilter,
                defaultOpen: true,
                detailsClass: 'yuutai-ext-filter-collapsible',
                bodyClass: 'yuutai-ext-filter-body'
            });
        }

        syncAllCollapsibles();

        setupTargetOptions();
        syncSettingsInputs();
        syncDeltaLimits();

        document.addEventListener('input', (event) => {
            if (event.target && (event.target.id === 'available-capital' || event.target.classList.contains('stock-checkbox'))) {
                debounceUpdate();
            }
        });
        document.addEventListener('change', (event) => {
            if (event.target && (event.target.classList.contains('stock-checkbox') || event.target.id === 'available-capital')) {
                debounceUpdate();
            }
        });
        document.querySelectorAll('.filter-btn').forEach((btn) => {
            btn.addEventListener('click', debounceUpdate);
        });

        updateAll();
    };

    init();
})();

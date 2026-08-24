/**
 * Client-side results renderer.
 *
 * Renders simulation results from JSON into HTML. This is the sole results
 * renderer: simulations run client-side via Pyodide and there is no
 * server-side results template.
 */

// Use `var` + idempotent guard because deck_store.js's navigateToSim() does
// document.write(html) which re-executes this script; `const` would throw
// "Identifier 'ClientResults' has already been declared" and abort the whole
// page bootstrap, leaving the simulate page non-functional.
var ClientResults = window.ClientResults || (function() {
    'use strict';

    let rampTradeoffContext = null;
    let curveValueContext = null;
    const pendingRampTradeoff = {};
    const pendingTurnStructure = {};

    // -- Tooltip management (shared with server-side rendering) --

    let tooltip = null;
    const tooltipCache = {};

    function ensureTooltip() {
        tooltip = document.getElementById('card-preview-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'card-preview-tooltip';
            document.body.appendChild(tooltip);
        }
    }

    function positionTooltip(e) {
        const x = e.clientX + 15;
        const y = Math.max(10, e.clientY - 180);
        tooltip.style.left = x + 'px';
        tooltip.style.top = y + 'px';
    }

    function rebindTooltips() {
        ensureTooltip();
        document.querySelectorAll('.card-link').forEach(link => {
            if (link._tooltipBound) return;
            link._tooltipBound = true;
            link.addEventListener('mouseenter', function(e) {
                const name = this.dataset.cardName;
                if (!tooltipCache[name]) {
                    const img = document.createElement('img');
                    img.src = 'https://api.scryfall.com/cards/named?exact='
                        + encodeURIComponent(name) + '&format=image&version=normal';
                    img.alt = name;
                    tooltipCache[name] = img;
                }
                tooltip.innerHTML = '';
                tooltip.appendChild(tooltipCache[name]);
                tooltip.style.display = 'block';
                positionTooltip(e);
            });
            link.addEventListener('mousemove', positionTooltip);
            link.addEventListener('mouseleave', function() {
                tooltip.style.display = 'none';
            });
        });
    }

    // -- HTML generation helpers --

    function fmt(val, decimals) {
        return Number(val).toFixed(decimals);
    }

    function formatSignedDelta(val, decimals) {
        return val > 0 ? '+' + fmt(val, decimals) : fmt(val, decimals);
    }

    function rampScenarioSentenceLabel(signets) {
        return signets === 0
            ? 'no ramp'
            : signets + ' Signet' + (signets === 1 ? '' : 's') + ' ramp';
    }

    // Engine bookkeeping suffix used to keep simulator card identities unique.
    const COPY_SUFFIX_RE = /\s*\(\d+\)\s*$/;
    function baseCardName(name) {
        return (name || '').replace(COPY_SUFFIX_RE, '');
    }

    function cardLink(name) {
        const base = baseCardName(name);
        return '<a class="card-link" data-card-name="' + escapeHtml(name)
            + '" href="https://scryfall.com/search?exact='
            + encodeURIComponent(base) + '" target="_blank">' + escapeHtml(base) + '</a>';
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatConfig(str) {
        // Render (mv2) portions as <sub> for compact display
        return escapeHtml(str).replace(/\(([^)]+)\)/g, '<sub>($1)</sub>');
    }

    // -- Section renderers --

    // Per-stat copy used by the CASTER Score header tooltip + explanation panel.
    const CASTER_STATS = [
        {name: 'Consistency', key: 'consistency', color: '#eab308',
         desc: 'How rarely the deck bricks',
         lowMeaning: 'worst-case games are catastrophic. Frequent floods, stalls, or dead hands.',
         highMeaning: 'almost every game runs smoothly. The bottom 25% looks much like the average.'},
        {name: 'Acceleration', key: 'acceleration', color: '#ef4444',
         desc: 'Early-game mana deployment',
         lowMeaning: 'slow opening. Barely any mana spent over the first four turns.',
         highMeaning: 'explosive early game with multiple ramp/draw plays before turn 5.'},
        {name: 'Snowball', key: 'snowball', color: '#8b5cf6',
         desc: 'How much advantage compounds over time',
         lowMeaning: 'late game stays flat. The deck does not pull away from its early curve.',
         highMeaning: 'late turns dwarf the early game. The deck snowballs hard once it gets going.'},
        {name: 'Tuning', key: 'tuning', color: '#22c55e',
         desc: 'How well the curve composition matches the ramp\'s pace per CMC',
         lowMeaning: 'ramp pace is paying for high-CMC slots the deck does not have enough of.',
         highMeaning: 'every CMC slot delivers what the ramp is paying for. Curve and ramp are in sync.'},
        {name: 'Efficiency', key: 'efficiency', color: '#3b82f6',
         desc: 'Whether the deck draws enough cards to spend its mana',
         lowMeaning: 'draw rate falls short of what is needed to spend the mana the deck generates.',
         highMeaning: 'draw rate keeps up with mana production. Nearly all generated mana gets spent.'},
        {name: 'Reach', key: 'reach', color: '#f97316',
         desc: 'Peak mana output and ceiling',
         lowMeaning: 'low ceiling. Even the best games never spend that much mana.',
         highMeaning: 'explosive peak turns. The top 25% of games spend a huge amount of mana.'},
    ];

    function renderCasterExplanation() {
        const cal = window.CASTER_CALIBRATION || {};

        let html = '<details class="caster-help">';
        html += '<summary>What does my CASTER Score mean?</summary>';
        html += '<div class="caster-help-body">';
        html += '<p>Each stat is scaled from 1 to 10 against ';
        if (cal.calibrated && cal.n_rows > 0) {
            html += 'an empirical distribution of ' + cal.n_rows + ' run'
                + (cal.n_rows === 1 ? '' : 's') + ' across '
                + cal.n_decks + ' deck' + (cal.n_decks === 1 ? '' : 's') + ' '
                + 'in this database. Anchors use p' + Math.round(cal.low_pct) + '/p'
                + Math.round(cal.high_pct) + ' with Bayesian shrinkage and pseudo_count='
                + cal.pseudo_count + '. ';
        } else {
            html += 'the built-in default anchors. No database calibration is available yet. ';
        }
        html += 'Score 1 matches the low anchor. Score 10 matches the high anchor.</p>';

        html += '<table class="caster-help-table"><thead><tr>'
            + '<th>Stat</th><th>What it measures</th>'
            + '<th>Score 1</th><th>Score 10</th>'
            + '</tr></thead><tbody>';
        for (const s of CASTER_STATS) {
            html += '<tr>';
            html += '<td style="color:' + s.color + '">' + s.name + '</td>';
            html += '<td>' + escapeHtml(s.desc) + '</td>';
            html += '<td>' + escapeHtml(s.lowMeaning) + '</td>';
            html += '<td>' + escapeHtml(s.highMeaning) + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
        if (!cal.calibrated) {
            html += '<p class="caster-help-foot"><code>AUTO_GOLDFISH_CALIBRATE=1</code> is the default. Run more decks to switch from default anchors to a live calibration.</p>';
        } else {
            html += '<p class="caster-help-foot">Calibration refreshes automatically as new runs land in the DB. '
                + 'Set <code>AUTO_GOLDFISH_CALIBRATE=0</code> to disable.</p>';
        }
        html += '</div></details>';
        return html;
    }

    // --- CASTER share card (client-side image; no server) ---
    // Data prep lives in caster_card.js (window.CasterCard) so it's testable.
    // The canvas drawing + share/clipboard glue below needs a real DOM.

    function _truncateToWidth(ctx, text, maxW) {
        text = String(text == null ? '' : text);
        if (ctx.measureText(text).width <= maxW) return text;
        while (text.length > 1 && ctx.measureText(text + '...').width > maxW) {
            text = text.slice(0, -1);
        }
        return text + '...';
    }

    // Compose a 1080x1080 PNG-able canvas: header, overall, radar, six stats.
    function drawCasterCard(data, radarCanvas) {
        const S = 1080;
        const sans = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        const c = document.createElement('canvas');
        c.width = S; c.height = S;
        const ctx = c.getContext('2d');

        ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, S, S);

        // Header band
        ctx.fillStyle = '#1a1a2e'; ctx.fillRect(0, 0, S, 160);
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'left';
        ctx.fillStyle = '#ffffff';
        ctx.font = '700 46px ' + sans;
        ctx.fillText('CASTER Score', 56, 64);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '400 30px ' + sans;
        ctx.fillText(_truncateToWidth(ctx, data.deckName, 560), 56, 116);
        ctx.textAlign = 'right';
        ctx.font = '600 28px ' + sans;
        ctx.fillText('auto-goldfish', S - 56, 80);

        // Overall headline
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        ctx.fillStyle = '#64748b';
        ctx.font = '600 30px ' + sans;
        ctx.fillText('OVERALL', 60, 250);
        ctx.fillStyle = '#1a1a2e';
        ctx.font = '800 150px ' + sans;
        const numStr = String(data.overall);
        ctx.fillText(numStr, 56, 380);
        const numW = ctx.measureText(numStr).width;
        ctx.fillStyle = '#94a3b8';
        ctx.font = '600 56px ' + sans;
        ctx.fillText('/ 10', 56 + numW + 24, 380);

        // Radar (centered square) - reuse the already-rendered Chart.js canvas
        if (radarCanvas && radarCanvas.width) {
            const rSize = 460;
            try { ctx.drawImage(radarCanvas, (S - rSize) / 2, 415, rSize, rSize); } catch (e) {}
        }

        // Six stats: 3 columns x 2 rows along the bottom
        const stats = data.stats || [];
        const colW = (S - 112) / 3;
        const baseY = 930;
        ctx.textBaseline = 'middle';
        for (let i = 0; i < stats.length; i++) {
            const x = 56 + (i % 3) * colW;
            const y = baseY + Math.floor(i / 3) * 78;
            ctx.beginPath();
            ctx.fillStyle = stats[i].color || '#64748b';
            ctx.arc(x + 12, y, 12, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#475569';
            ctx.font = '500 26px ' + sans;
            ctx.textAlign = 'left';
            ctx.fillText(stats[i].name, x + 36, y);
            ctx.fillStyle = '#1a1a2e';
            ctx.font = '800 32px ' + sans;
            ctx.textAlign = 'right';
            ctx.fillText(String(stats[i].value), x + colW - 28, y);
        }
        return c;
    }

    function _downloadCard(blob, fname) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = fname;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }

    function _copyOrDownload(blob, fname, setStatus) {
        if (navigator.clipboard && typeof window.ClipboardItem !== 'undefined') {
            navigator.clipboard.write([new window.ClipboardItem({'image/png': blob})])
                .then(function () { setStatus('Copied! Paste it anywhere.'); })
                .catch(function () { _downloadCard(blob, fname); setStatus('Image downloaded.'); });
        } else {
            _downloadCard(blob, fname);
            setStatus('Image downloaded.');
        }
    }

    // Progressive enhancement: native share sheet (mobile) -> clipboard -> download.
    function shareCasterCard(data, statusEl) {
        function setStatus(msg) { if (statusEl) statusEl.textContent = msg || ''; }
        let canvas;
        try {
            canvas = drawCasterCard(data, document.getElementById('deckScoreRadar'));
        } catch (e) {
            setStatus('Could not build the card.');
            return;
        }
        setStatus('Preparing...');
        canvas.toBlob(function (blob) {
            if (!blob) { setStatus('Could not build the card.'); return; }
            const fname = String(data.deckName || 'deck').replace(/[^a-z0-9_-]+/gi, '_') + '-caster.png';
            let file = null;
            try { file = new File([blob], fname, {type: 'image/png'}); } catch (e) { file = null; }

            if (file && navigator.canShare && navigator.canShare({files: [file]})) {
                navigator.share({
                    files: [file],
                    title: 'CASTER Score',
                    text: data.deckName + ' - CASTER ' + data.overall + '/10'
                }).then(function () { setStatus('Shared.'); })
                  .catch(function (err) {
                      if (err && err.name === 'AbortError') { setStatus(''); }
                      else { _copyOrDownload(blob, fname, setStatus); }
                  });
                return;
            }
            _copyOrDownload(blob, fname, setStatus);
        }, 'image/png');
    }

    // Wire the Share button after the radar canvas has been rendered.
    function wireCasterShare(results, deckName) {
        const btn = document.querySelector('.caster-share-btn');
        if (!btn) return;
        const r = (results && results.length) ? results[results.length - 1] : null;
        const score = r && r.deck_score;
        if (!score || typeof window.CasterCard === 'undefined') {
            const row = document.querySelector('.caster-share-row');
            if (row) row.style.display = 'none';
            return;
        }
        const statusEl = document.querySelector('.caster-share-status');
        const data = CasterCard.cardData(score, deckName, CASTER_STATS);
        btn.addEventListener('click', function () { shareCasterCard(data, statusEl); });
    }

    function renderDeckScore(results) {
        // Use the last result (highest land count) for the score
        const r = results[results.length - 1];
        const score = r.deck_score;
        if (!score) return '';

        // Overall headline: plain mean of the six axes. Prefer the value the
        // engine computed (score.overall); fall back to a client-side mean so
        // older cached results still show a headline.
        let overall = score.overall;
        if (typeof overall !== 'number') {
            const vals = CASTER_STATS.map(s => score[s.key] || 0);
            overall = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10;
        }

        let html = '<div class="deck-score-section"><h2>CASTER Score</h2>';
        html += '<div class="caster-overall" title="Plain mean of the six axes below. The six-stat profile is the real picture.">'
            + '<span class="caster-overall-num">' + overall + '</span>'
            + '<span class="caster-overall-max">/ 10</span>'
            + '<span class="caster-overall-label">Overall</span>'
            + '</div>';
        html += '<div class="caster-share-row">'
            + '<button type="button" class="btn btn-secondary btn-sm caster-share-btn">Share score card</button>'
            + '<span class="caster-share-status hint" role="status" aria-live="polite"></span>'
            + '</div>';
        html += renderCasterExplanation();
        html += '<div class="deck-score-grid">';
        // Radar chart canvas
        html += '<div class="deck-score-radar"><canvas id="deckScoreRadar"></canvas></div>';
        // Stat bars
        html += '<div class="deck-score-bars">';
        for (const s of CASTER_STATS) {
            const val = score[s.key] || 0;
            const pct = (val / 10 * 100).toFixed(0);
            html += '<div class="deck-stat-row">';
            html += '<div class="deck-stat-label" data-tip="' + escapeHtml(s.desc) + '">' + s.name + '</div>';
            html += '<div class="deck-stat-bar-track">';
            html += '<div class="deck-stat-bar-fill" style="width:' + pct + '%;background:' + s.color + '"></div>';
            html += '</div>';
            html += '<div class="deck-stat-value">' + val + '</div>';
            html += '</div>';
        }
        html += '</div></div></div>';
        return html;
    }

    function renderCurveValue(results) {
        const r = results[results.length - 1];
        const cv = r && r.curve_value;
        if (!cv || !cv.implied_draw) return '';
        const id_ = cv.implied_draw;
        const isv = cv.implied_spell_value || {};
        const deficit = id_.actual_deficit || 0;
        const deficitPos = deficit >= 0.05;
        const noRamp = !!isv.no_ramp;

        let html = '<div class="curve-value-section">';
        html += '<h2>Curve Value Analysis</h2>';

        // Help block
        html += '<details class="curve-value-help"><summary>What does this mean?</summary>';
        html += '<div class="curve-value-help-body">';
        html += '<p>Implied Draw estimates how many cards the deck needs to see by each turn to hit land drops, find committed ramp, and still have spendable spells.</p>';
        html += '<ul>';
        html += '<li>Need either way: the overlap between the land and spell requirements.</li>';
        html += '<li>Extra for lands: the gap when land drops are the bottleneck.</li>';
        html += '<li>Extra for spells: the gap when spendable spells are the bottleneck.</li>';
        html += '</ul>';
        html += '<p>The orange line is actual average cards drawn. The grey dashed line is natural draw. The table under the chart shows the per-turn breakdown.</p>';
        const verdictForHelp = cv.curve_verdict;
        const helpNoRamp = !!(verdictForHelp && verdictForHelp.no_ramp);
        html += '<p>Implied Spell Value compares two views of each CMC slot:</p>';
        html += '<ul>';
        html += '<li>A required: the bar each CMC slot needs to clear.</li>';
        html += '<li>B deck implies: what the curve delivers in simulation.</li>';
        html += '</ul>';
        html += '<p>When B is lower than A, the slot is ramp over-aggressive. When B is higher than A, the slot has slack.</p>';
        html += '<p>The headline badge is net mana-turns at flat power. Positive means ramp pays for itself before any high-CMC payoff. Negative means high-CMC slots must compensate.</p>';
        if (helpNoRamp) {
            html += '<p>No permanent ramp, so the bar collapses to 1&times; everywhere. A is measuring per-slot mana efficiency.</p>';
        }
        html += '</div></details>';

        const ts = cv.turn_structure;
        if (ts && ts.rows && ts.rows.length > 0) {
            const valueDelta = ts.delta_value_mana_spent || 0;
            const deltaClass = valueDelta > 0.05 ? 'pos' : (valueDelta < -0.05 ? 'neg' : 'flat');
            html += '<div class="curve-value-turn-spend">';
            html += '<div class="cv-turn-spend-head">';
            html += '<h3>Curve Out Timeline</h3>';
            html += '<div class="curve-value-summary-row">';
            html += '<span class="cv-stat"><span class="cv-label">Total mana spent with current ramp</span> <strong>' + fmt(ts.with_ramp_total_value_mana_spent || 0, 1) + '</strong></span>';
            html += '</div></div>';
            html += '<div class="cv-turn-spend-charts">';
            html += '<div class="curve-value-turn-chart-wrap cv-turn-spend-chart-wrap"><canvas id="curveValueTurnSpendWithRampChart"></canvas></div>';
            html += '</div>';
            const currentSignets = parseInt(((r.ramp_tradeoff_input || {}).current_rocks || 0), 10);
            if (currentSignets > 0) {
                html += '<div class="lazy-panel-prompt cv-less-ramp-control">';
                html += '<span>Would you like to see this with less ramp?</span>';
                html += '<select id="curveValueLessRampSelect">';
                for (let signets = 0; signets < currentSignets; signets++) {
                    const label = signets === 0 ? 'No ramp' : (signets + ' Signet' + (signets === 1 ? '' : 's'));
                    html += '<option value="' + signets + '"' + (signets === 0 ? ' selected' : '') + '>' + label + '</option>';
                }
                html += '</select>';
                html += '<button type="button" class="btn btn-secondary btn-sm" id="curveValueLessRampBtn">Show scenario</button>';
                html += '</div>';
                html += '<div id="curveValueLessRampResult" class="cv-lazy-result" style="display:none;"></div>';
            }
            html += '<p class="cv-hint">Bars compare spendable spell mana by CMC, ramp setup mana, and unspent mana. Spendable includes draw spells, value spells, and commanders. Ramp is tracked separately. CMC colors run from low-cost blue to high-cost orange.</p>';
            html += '</div>';
        }

        html += '<div class="curve-value-grid">';

        // Implied Draw
        html += '<div class="curve-value-draw">';
        html += '<h3>Curve Implications</h3>';
        html += '<div class="curve-value-summary-row">';
        html += '<span class="cv-stat"><span class="cv-label">Cards needed</span> <strong>' + fmt(id_.N_max, 1) + '</strong></span>';
        html += '<span class="cv-stat"><span class="cv-label">Actually drawn</span> <strong>' + fmt(id_.actual_total_draws || 0, 1) + '</strong></span>';
        const deficitClass = deficitPos ? 'cv-deficit-pos' : 'cv-deficit-ok';
        html += '<span class="cv-stat ' + deficitClass + '"><span class="cv-label">Deficit</span> <strong>' + fmt(deficit, 1) + '</strong></span>';
        html += '</div>';
        html += '<div class="curve-value-chart-wrap"><canvas id="curveValueDrawChart"></canvas></div>';
        // Per-turn breakdown table (ground truth for the chart).
        const idLands = id_.per_turn_lands_required || [];
        const idValue = id_.per_turn_value_required || [];
        const idReq = id_.per_turn_required || [];
        const idActual = id_.per_turn_actual || [];
        if (idLands.length > 0) {
            html += '<details class="cv-breakdown-details">';
            html += '<summary>Per-turn breakdown</summary>';
            html += '<table class="cv-breakdown-table"><thead><tr>';
            html += '<th>Turn</th><th>Lands req</th><th>Spells req</th><th>Required = max</th><th>Active</th><th>Actual MC</th>';
            html += '</tr></thead><tbody>';
            for (let t = 0; t < idLands.length; t++) {
                const L = idLands[t] || 0;
                const V = idValue[t] || 0;
                const req = idReq[t] || Math.max(L, V);
                const dom = V > L ? 'spells' : 'lands';
                const act = idActual[t];
                html += '<tr>';
                html += '<td>' + (t + 1) + '</td>';
                html += '<td>' + fmt(L, 2) + '</td>';
                html += '<td>' + fmt(V, 2) + '</td>';
                html += '<td><strong>' + fmt(req, 2) + '</strong></td>';
                html += '<td class="cv-active-' + dom + '">' + dom + '</td>';
                html += '<td>' + (act != null ? fmt(act, 2) : '-') + '</td>';
                html += '</tr>';
            }
            html += '</tbody></table></details>';
        }
        // Convert deficit in cards to mana of value spells unspent.
        // Each missing card averages (V/D) × V_avg_cmc mana of value spending.
        const valuePerCard = id_.D > 0 ? (id_.V_avg_cmc * id_.V / id_.D) : 0;
        const deficitMana = deficit * valuePerCard;
        const actualDraws = id_.actual_total_draws || 0;
        if (deficitPos) {
            html += '<p class="cv-hint">';
            html += 'Deficit: your deck draws about ' + fmt(actualDraws, 1) + ' cards per game, ';
            html += fmt(deficit, 1) + ' short of the ' + fmt(id_.N_max, 1) + '-card analytical requirement. ';
            html += 'With your value pool\'s avg cost of ' + fmt(id_.V_avg_cmc, 2) + ' mana and ' + id_.V + '/' + id_.D + ' share of the deck, ';
            html += 'each missing card averages ' + fmt(valuePerCard, 2) + ' mana of value-spell spending ';
            html += 'That translates to roughly ' + fmt(deficitMana, 1) + ' mana of value spells going unspent per game on average.';
            html += '</p>';
        } else {
            html += '<p class="cv-hint">';
            html += 'Your deck draws about ' + fmt(actualDraws, 1) + ' cards per game, ';
            html += 'meeting the ' + fmt(id_.N_max, 1) + '-card analytical requirement. ';
            html += 'Value mana is fully spent in expectation. There is no significant late-game waste.';
            html += '</p>';
        }
        html += '<div class="lazy-panel-prompt">';
        html += '<span>Would you like to see the spell value implied by your ramp suite?</span>';
        html += '<button type="button" class="btn btn-secondary btn-sm" id="curveValuePowerBtn">Show spell value</button>';
        html += '</div>';
        html += '</div>';

        // Implied Spell Value (A vs B verdict)
        html += '<div id="curveValuePowerPanel" class="curve-value-power" style="display:none;">';
        html += '<h3>Implied Spell Value</h3>';
        const verdict = cv.curve_verdict;
        if (verdict) {
            const baseline = verdict.baseline_cmc;
            if (verdict.no_ramp) {
                html += '<p class="cv-rate-line">No permanent ramp. The bar collapses to 1&times; everywhere.</p>';
            } else {
                const excess = (verdict.idealized_excess != null ? verdict.idealized_excess : 0).toFixed(0);
                const strength = ((verdict.ramp_share || 0) * 100).toFixed(0);
                html += '<p class="cv-rate-line">Ramp produces <strong>+' + excess + ' mana</strong> over the game';
                html += ' &nbsp;&middot;&nbsp; bar at <strong>' + strength + '%</strong> strength</p>';
            }

            const netFlat = verdict.net_flat || 0;
            const netPos = netFlat > 0.5;
            const netNeg = netFlat < -0.5;
            const netClass = netPos ? 'pos' : (netNeg ? 'neg' : 'flat');
            html += '<div class="cv-net-badge cv-net-' + netClass + '">';
            if (netPos) {
                html += '&check; Ramp is net-positive at flat power: <strong>+' + netFlat.toFixed(0) + ' mana-turns</strong>. ';
                html += 'Per-CMC gaps below show where extra power is still required.';
            } else if (netNeg) {
                html += '&#9888; Ramp loses <strong>' + Math.abs(netFlat).toFixed(0) + ' mana-turns</strong> at flat power. The gaps below show which slots must compensate.';
            } else {
                html += 'Ramp is roughly self-paying at flat power. Net is about 0 mana-turns.';
            }
            html += '</div>';

            html += '<div class="curve-value-power-chart-wrap"><canvas id="curveValuePowerChart"></canvas></div>';

            html += '<table class="cv-power-table"><thead><tr>';
            html += '<th>CMC</th><th>Cards</th><th>A required</th><th>B deck implies</th><th>Reading</th>';
            html += '</tr></thead><tbody>';
            const rows = verdict.rows || [];
            for (const row of rows) {
                const kindClass = 'cv-row-' + (row.kind || '').replace(/_/g, '-');
                const aTxt = (row.a_required != null && isFinite(row.a_required)) ? (fmt(row.a_required, 2) + '&times;') : '-';
                const bTxt = (row.b_implicit != null && isFinite(row.b_implicit)) ? (fmt(row.b_implicit, 2) + '&times;') : '-';
                html += '<tr class="' + kindClass + '">';
                html += '<td>' + row.cmc + '</td>';
                html += '<td>' + Math.round(row.n_cards || 0) + '</td>';
                html += '<td>' + aTxt + '</td>';
                html += '<td>' + bTxt + '</td>';
                html += '<td class="cv-reading-cell">';
                if (row.kind === 'baseline') {
                    html += '<span class="cv-tag cv-tag-base">baseline</span>';
                } else if (row.kind === 'below_baseline') {
                    html += '<span class="cv-tag cv-tag-base">below baseline</span>';
                } else if (row.kind === 'coherent') {
                    html += '<span class="cv-tag cv-tag-ok">&check; coherent</span>';
                    html += '<small class="cv-action">Your ' + row.cmc + '-drops match the bar.</small>';
                } else if (row.kind === 'ramp_over_aggressive') {
                    const gap = row.gap || 1;
                    html += '<span class="cv-tag cv-tag-warn">&#9888; gap ' + gap.toFixed(1) + '&times;</span>';
                    html += '<small class="cv-action">Your ' + row.cmc + '-drops are ' + gap.toFixed(1) + '&times; short. Cut a ramp piece to soften the bar. Any cut helps, and cutting fast ramp like Sol Ring helps most.</small>';
                } else if (row.kind === 'over_allocated') {
                    const slack = row.slack || 1;
                    html += '<span class="cv-tag cv-tag-slack">&check; slack ' + fmt(slack, 2) + '&times;</span>';
                    html += '<small class="cv-action">Your ' + row.cmc + '-drops have slack. These slots can be weaker without hurting coherence.</small>';
                } else if (row.kind === 'no_slots') {
                    html += '<span class="cv-tag cv-tag-base">no slots</span>';
                }
                html += '</td>';
                html += '</tr>';
            }
            html += '</tbody></table>';

            html += '<p class="cv-hint">';
            html += '<strong>A</strong> = the bar your ramp sets. <strong>B</strong> = what your curve delivers. ';
            html += 'When B falls short of A, cutting ramp softens the bar. When B exceeds A, you have slack to use weaker cards.';
            html += '</p>';
        } else {
            html += '<p class="cv-hint">No value spells in deck. Verdict undefined.</p>';
        }
        html += '</div>';  // power

        html += '</div></div>';  // grid, section
        return html;
    }

    function uniqueSortedCmcs(rows) {
        const seen = {};
        for (const row of (rows || [])) {
            if (row.cmc != null) seen[String(row.cmc)] = true;
        }
        return Object.keys(seen).map(function(x) { return parseInt(x, 10); })
            .filter(function(x) { return !isNaN(x); })
            .sort(function(a, b) { return a - b; });
    }

    function mixRgb(a, b, p) {
        return [
            Math.round(a[0] + (b[0] - a[0]) * p),
            Math.round(a[1] + (b[1] - a[1]) * p),
            Math.round(a[2] + (b[2] - a[2]) * p),
        ];
    }

    function cmcGradientColor(cmc, cmcs) {
        if (!cmcs || cmcs.length <= 1) return 'rgb(37, 99, 235)';
        const idx = Math.max(0, cmcs.indexOf(cmc));
        const p = idx / Math.max(1, cmcs.length - 1);
        const stops = [
            [37, 99, 235],
            [22, 163, 74],
            [249, 115, 22],
        ];
        const rgb = p <= 0.5
            ? mixRgb(stops[0], stops[1], p / 0.5)
            : mixRgb(stops[1], stops[2], (p - 0.5) / 0.5);
        return 'rgb(' + rgb[0] + ', ' + rgb[1] + ', ' + rgb[2] + ')';
    }

    function turnValue(ts, path, turnIdx, cmc) {
        const turns = ts[path] || [];
        const row = turns[turnIdx] || {};
        return row[String(cmc)] || row[cmc] || 0;
    }

    function turnValueTotal(ts, path, turnIdx, cmcs) {
        return cmcs.reduce(function(total, cmc) {
            return total + turnValue(ts, path, turnIdx, cmc);
        }, 0);
    }

    function turnSpendChartData(ts) {
        const cmcs = uniqueSortedCmcs(ts.rows);
        const turns = ts.T || Math.max(
            (ts.with_ramp_value_spend_by_turn || []).length,
            (ts.counterfactual_value_spend_by_turn || []).length
        );
        const labels = [];
        for (let t = 1; t <= turns; t++) labels.push('T' + t);

        let yMax = 0;
        for (let i = 0; i < turns; i++) {
            yMax = Math.max(
                yMax,
                turnValueTotal(ts, 'with_ramp_value_spend_by_turn', i, cmcs)
                    + ((ts.with_ramp_ramp_spend || [])[i] || 0)
                    + ((ts.with_ramp_unused_mana || [])[i] || 0),
                turnValueTotal(ts, 'counterfactual_value_spend_by_turn', i, cmcs)
                    + ((ts.counterfactual_unused_mana || [])[i] || 0)
            );
        }
        yMax = yMax > 0 ? yMax * 1.08 : undefined;

        return {cmcs: cmcs, labels: labels, yMax: yMax};
    }

    function renderTurnSpendScenarioChart(canvas, ts, title, valuePath, unusedValues, rampValues, yMaxOverride) {
        if (!canvas || !ts || !ts.rows || ts.rows.length === 0) return;
        const chartData = turnSpendChartData(ts);
        const labels = chartData.labels;
        const cmcs = chartData.cmcs;
        const datasets = [];
        for (const cmc of cmcs) {
            const color = cmcGradientColor(cmc, cmcs);
            datasets.push({
                label: 'CMC ' + cmc,
                data: labels.map(function(_label, i) {
                    return turnValue(ts, valuePath, i, cmc);
                }),
                stack: 'mana',
                backgroundColor: color,
                borderColor: '#ffffff',
                borderWidth: 1,
            });
        }
        if (rampValues) {
            datasets.push({
                label: 'ramp setup',
                data: rampValues,
                stack: 'mana',
                backgroundColor: 'rgba(100, 116, 139, 0.85)',
                borderColor: '#ffffff',
                borderWidth: 1,
            });
        }
        datasets.push({
            label: 'unspent mana',
            data: unusedValues || [],
            stack: 'mana',
            backgroundColor: 'rgba(226, 232, 240, 0.75)',
            borderColor: '#cbd5e1',
            borderWidth: 1,
        });

        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        new Chart(canvas, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                categoryPercentage: 0.82,
                barPercentage: 0.88,
                plugins: {
                    title: {
                        display: true,
                        text: title,
                    },
                    tooltip: {
                        callbacks: {
                            title: function(items) {
                                const label = items[0] && items[0].label ? items[0].label : '';
                                return label + ' / ' + title;
                            },
                            label: function(item) {
                                const label = item.dataset && item.dataset.label ? item.dataset.label : '';
                                const value = item.parsed && item.parsed.y ? item.parsed.y : 0;
                                return label + ': ' + Number(value).toFixed(1);
                            },
                            footer: function(items) {
                                const total = items.reduce(function(sum, item) {
                                    const value = item.parsed && item.parsed.y ? item.parsed.y : 0;
                                    return sum + Number(value);
                                }, 0);
                                return 'Total: ' + total.toFixed(1);
                            },
                        },
                    },
                },
                scales: {
                    x: { stacked: true, title: { display: true, text: 'Turn' } },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        max: yMaxOverride || chartData.yMax,
                        title: { display: true, text: 'Spendable mana / available' },
                    },
                },
            },
        });
    }

    function renderCurveValueTurnSpendChart(results) {
        const withRampCanvas = document.getElementById('curveValueTurnSpendWithRampChart');
        if (!withRampCanvas) return;
        const r = results[results.length - 1];
        const cv = r && r.curve_value;
        const ts = cv && cv.turn_structure;
        if (!ts || !ts.rows || ts.rows.length === 0) return;

        renderTurnSpendScenarioChart(
            withRampCanvas,
            ts,
            'With current ramp',
            'with_ramp_value_spend_by_turn',
            ts.with_ramp_unused_mana || [],
            ts.with_ramp_ramp_spend || []
        );
    }

    function renderCurveValueChart(results) {
        const canvas = document.getElementById('curveValueDrawChart');
        if (!canvas) return;
        const r = results[results.length - 1];
        const cv = r && r.curve_value;
        if (!cv || !cv.implied_draw) return;
        const id_ = cv.implied_draw;
        const lands = id_.per_turn_lands_required || [];
        const value = id_.per_turn_value_required || [];
        const actual = id_.per_turn_actual || [];
        const natural = id_.per_turn_natural || [];
        const turns = lands.length;
        const labels = [];
        for (let t = 1; t <= turns; t++) labels.push('T' + t);

        // Stacked decomposition: at each turn,
        //   floor    = min(lands, value)  -- both bottlenecks require this
        //   lands_ex = max(0, lands - value)  -- extra from land constraint
        //   value_ex = max(0, value - lands)  -- extra from value constraint
        // Exactly one of lands_ex / value_ex is non-zero per turn, so the
        // stack always sums to max(lands, value) = per_turn_required and
        // both bottlenecks remain individually visible (smaller as floor,
        // larger as a colored cap on top).
        const floor = lands.map((l, i) => Math.min(l, value[i] || 0));
        const lands_ex = lands.map((l, i) => Math.max(0, l - (value[i] || 0)));
        const value_ex = value.map((v, i) => Math.max(0, v - (lands[i] || 0)));

        const existing = Chart.getChart('curveValueDrawChart');
        if (existing) existing.destroy();

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Cards you need either way',
                        data: floor,
                        borderColor: '#64748b',
                        backgroundColor: 'rgba(148, 163, 184, 0.25)',
                        borderWidth: 1,
                        fill: 'origin',
                        tension: 0.2,
                        pointRadius: 0,
                        stack: 'required',
                    },
                    {
                        label: 'Extra cards to draw enough lands',
                        data: lands_ex,
                        borderColor: '#1d4ed8',
                        backgroundColor: 'rgba(37, 99, 235, 0.65)',
                        borderWidth: 1,
                        fill: '-1',
                        tension: 0.2,
                        pointRadius: 0,
                        stack: 'required',
                    },
                    {
                        label: 'Extra cards to draw enough spells',
                        data: value_ex,
                        borderColor: '#7e22ce',
                        backgroundColor: 'rgba(168, 85, 247, 0.65)',
                        borderWidth: 1,
                        fill: '-1',
                        tension: 0.2,
                        pointRadius: 0,
                        stack: 'required',
                    },
                    {
                        label: 'Natural draw (no draw spells)',
                        data: natural,
                        borderColor: '#94a3b8',
                        backgroundColor: '#94a3b8',
                        borderWidth: 1,
                        borderDash: [3, 3],
                        fill: false,
                        tension: 0,
                        pointRadius: 0,
                        stack: 'natural',
                        order: 2,
                    },
                    {
                        label: 'Actual cards drawn (MC avg)',
                        data: actual,
                        borderColor: '#f59e0b',
                        backgroundColor: '#f59e0b',
                        borderWidth: 2.5,
                        fill: false,
                        tension: 0.2,
                        pointRadius: 3,
                        stack: 'actual',
                        order: 1,
                    },
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: { display: true, text: 'Cumulative cards: needed (lands & value bottlenecks) vs. drawn' },
                    tooltip: {
                        callbacks: {
                            footer: function(items) {
                                const idx = items[0] ? items[0].dataIndex : 0;
                                const landsVal = lands[idx] || 0;
                                const spellsVal = value[idx] || 0;
                                const actualVal = actual[idx];
                                const required = Math.max(landsVal, spellsVal);
                                const dominant = spellsVal > landsVal ? 'spells' : 'lands';
                                let footer = 'Lands need: ' + landsVal.toFixed(2)
                                    + '   Spells need: ' + spellsVal.toFixed(2)
                                    + '\nRequired = max = ' + required.toFixed(2)
                                    + ' (' + dominant + ' dominates)';
                                if (actualVal != null) {
                                    const diff = required - actualVal;
                                    const sign = diff > 0 ? '+' : '';
                                    footer += '\nDeficit vs actual: ' + sign + diff.toFixed(2);
                                }
                                return footer;
                            }
                        }
                    }
                },
                scales: {
                    x: { title: { display: true, text: 'Turn' } },
                    y: { title: { display: true, text: 'Cumulative cards' }, beginAtZero: true, stacked: true }
                }
            }
        });
    }

    function renderCurveValuePowerChart(results) {
        const canvas = document.getElementById('curveValuePowerChart');
        if (!canvas) return;
        const r = results[results.length - 1];
        const cv = r && r.curve_value;
        if (!cv || !cv.curve_verdict) return;
        const verdict = cv.curve_verdict;
        const rows = (verdict.rows || []).filter(function(row) { return row.cmc != null; });
        if (rows.length === 0) return;

        const labels = rows.map(function(row) { return 'c=' + row.cmc; });
        const aVals = rows.map(function(row) {
            const v = row.a_required;
            return (v == null || !isFinite(v)) ? null : v;
        });
        const bVals = rows.map(function(row) {
            const v = row.b_implicit;
            return (v == null || !isFinite(v)) ? null : v;
        });
        const gapLabels = rows.map(function(row) {
            return (row.kind === 'ramp_over_aggressive' && row.gap != null)
                ? ('gap ' + row.gap.toFixed(1) + '×') : '';
        });

        const existing = Chart.getChart('curveValuePowerChart');
        if (existing) existing.destroy();

        const gapLabelPlugin = {
            id: 'gapLabelPlugin',
            afterDatasetsDraw: function(chart) {
                const ctx = chart.ctx;
                const meta0 = chart.getDatasetMeta(0);
                const meta1 = chart.getDatasetMeta(1);
                ctx.save();
                ctx.font = 'bold 11px sans-serif';
                ctx.fillStyle = '#dc2626';
                ctx.textAlign = 'center';
                for (let i = 0; i < gapLabels.length; i++) {
                    const lbl = gapLabels[i];
                    if (!lbl) continue;
                    const a = meta0.data[i];
                    const b = meta1.data[i];
                    if (!a || !b) continue;
                    const x = (a.x + b.x) / 2;
                    const y = Math.min(a.y, b.y) - 6;
                    ctx.fillText(lbl, x, y);
                }
                ctx.restore();
            }
        };

        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'A required, your ramp\'s pace',
                        data: aVals,
                        backgroundColor: '#3b82f6',
                        borderColor: '#1d4ed8',
                        borderWidth: 1,
                    },
                    {
                        label: 'B, what your deck implies',
                        data: bVals,
                        backgroundColor: '#f59e0b',
                        borderColor: '#b45309',
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: {
                        display: true,
                        text: 'Required (A) vs. Deck-implied (B) intrinsic-power multiplier per CMC',
                    },
                    tooltip: {
                        callbacks: {
                            footer: function(items) {
                                const idx = items[0] ? items[0].dataIndex : 0;
                                const row = rows[idx];
                                if (!row) return '';
                                if (row.kind === 'coherent') return '✓ coherent';
                                if (row.kind === 'ramp_over_aggressive' && row.gap != null) {
                                    return '⚠ ramp over-aggressive (gap ' + row.gap.toFixed(2) + '×)';
                                }
                                if (row.kind === 'over_allocated' && row.slack != null) {
                                    return '✓ over-allocated (slack ' + row.slack.toFixed(2) + '×)';
                                }
                                if (row.kind === 'baseline') return 'baseline';
                                if (row.kind === 'below_baseline') return 'below baseline';
                                return '';
                            },
                        },
                    },
                },
                scales: {
                    x: { title: { display: true, text: 'Spell CMC' } },
                    y: {
                        title: { display: true, text: 'Multiplier vs. ' + verdict.baseline_cmc + '-drop' },
                        beginAtZero: true,
                    },
                },
            },
            plugins: [gapLabelPlugin],
        });
    }

    function initCurveValueLazyPanels(results, options) {
        options = options || {};
        const result = results && results.length ? results[results.length - 1] : null;
        curveValueContext = {
            result: result,
            worker: options.worker,
            deckJson: options.deckJson,
            config: options.config || {},
            results: results,
        };

        const powerBtn = document.getElementById('curveValuePowerBtn');
        const powerPanel = document.getElementById('curveValuePowerPanel');
        if (powerBtn && powerPanel) {
            powerBtn.addEventListener('click', function() {
                powerPanel.style.display = 'block';
                powerBtn.closest('.lazy-panel-prompt').style.display = 'none';
                renderCurveValuePowerChart(results);
            });
        }

        const lessRampBtn = document.getElementById('curveValueLessRampBtn');
        const lessRampSelect = document.getElementById('curveValueLessRampSelect');
        if (lessRampBtn && lessRampSelect) {
            lessRampBtn.addEventListener('click', function() {
                const target = parseInt(lessRampSelect.value, 10);
                const out = document.getElementById('curveValueLessRampResult');
                if (!out || isNaN(target)) return;
                out.style.display = 'block';
                out.innerHTML = '<div class="rt-loading">Computing timeline...</div>';
                if (!requestTurnStructureVariant(target)) {
                    out.innerHTML = '<div class="rt-suppressed">This timeline is not available in this view.</div>';
                }
            });
        }
    }

    function requestTurnStructureVariant(targetSignets) {
        if (!curveValueContext || !curveValueContext.worker || !curveValueContext.result) return false;
        const result = curveValueContext.result;
        if (!result.ramp_tradeoff_input) return false;
        const requestId = 'ts-' + Date.now() + '-' + targetSignets;
        pendingTurnStructure[requestId] = targetSignets;
        const config = Object.assign({}, curveValueContext.config, {
            ramp_tradeoff_input: result.ramp_tradeoff_input,
            target_signets: targetSignets,
        });
        curveValueContext.worker.postMessage({
            type: 'turn_structure_variant',
            requestId: requestId,
            deckJson: curveValueContext.deckJson || '[]',
            signatureJson: JSON.stringify(result.mean_cumulative_draws_per_turn || []),
            configJson: JSON.stringify(config),
        });
        return true;
    }

    function handleTurnStructureVariantResult(msg) {
        const targetSignets = msg.data && msg.data.target_signets != null
            ? msg.data.target_signets : pendingTurnStructure[msg.requestId];
        delete pendingTurnStructure[msg.requestId];
        const out = document.getElementById('curveValueLessRampResult');
        if (!out) return;
        const ts = msg.data && msg.data.turn_structure;
        if (!ts) {
            out.innerHTML = '<div class="rt-suppressed">Timeline could not be computed.</div>';
            return;
        }
        const title = targetSignets === 0
            ? 'No ramp'
            : targetSignets + ' Signet' + (targetSignets === 1 ? '' : 's');
        const scenarioTotal = ts.with_ramp_total_value_mana_spent || 0;
        const currentTs = curveValueContext
            && curveValueContext.result
            && curveValueContext.result.curve_value
            && curveValueContext.result.curve_value.turn_structure;
        const currentTotal = currentTs ? (currentTs.with_ramp_total_value_mana_spent || 0) : 0;
        const valueDelta = scenarioTotal - currentTotal;
        const deltaClass = valueDelta > 0.05 ? 'pos' : (valueDelta < -0.05 ? 'neg' : 'flat');
        const displayDelta = deltaClass === 'flat' ? 0 : valueDelta;
        out.innerHTML = '<div class="curve-value-summary-row">'
            + '<span class="cv-stat"><span class="cv-label">Total mana spent with ' + escapeHtml(rampScenarioSentenceLabel(targetSignets)) + '</span> <strong>' + fmt(scenarioTotal, 1) + '</strong></span>'
            + '<span class="cv-stat cv-delta-' + deltaClass + '"><span class="cv-label">Delta vs current ramp</span> <strong>' + formatSignedDelta(displayDelta, 1) + '</strong></span>'
            + '</div>'
            + '<div class="curve-value-turn-chart-wrap cv-turn-spend-chart-wrap"><canvas id="curveValueTurnSpendScenarioChart"></canvas></div>';
        renderTurnSpendScenarioChart(
            document.getElementById('curveValueTurnSpendScenarioChart'),
            ts,
            title,
            'with_ramp_value_spend_by_turn',
            ts.with_ramp_unused_mana || [],
            ts.with_ramp_ramp_spend || []
        );
    }

    function handleTurnStructureVariantError(msg) {
        delete pendingTurnStructure[msg.requestId];
        const out = document.getElementById('curveValueLessRampResult');
        if (out) {
            out.innerHTML = '<div class="rt-suppressed">Timeline could not be computed: '
                + escapeHtml(msg.message || 'unknown error') + '</div>';
        }
    }

    function initialRampTradeoffIndex(results) {
        for (let i = results.length - 1; i >= 0; i--) {
            if (results[i] && results[i].ramp_tradeoff) return i;
        }
        return Math.max(0, results.length - 1);
    }

    function rampTradeoffLandChoices(results) {
        const byLand = {};
        for (let i = 0; i < results.length; i++) {
            const r = results[i];
            if (!r || !r.ramp_tradeoff_input || r.land_count == null) continue;
            const key = String(r.land_count);
            if (byLand[key] == null || (r.ramp_tradeoff && !results[byLand[key]].ramp_tradeoff)) {
                byLand[key] = i;
            }
        }
        return Object.keys(byLand)
            .map(function(land) { return {land_count: parseInt(land, 10), index: byLand[land]}; })
            .sort(function(a, b) { return a.land_count - b.land_count; });
    }

    function formatSignetVariantLabel(label) {
        if (label === 'no_ramp') return 'No ramp';
        return String(label || '')
            .replace(/rock[- ]equivalent/g, 'Signet-equivalent')
            .replace(/rocks/g, 'Signets')
            .replace(/rock/g, 'Signet');
    }

    function renderRampTradeoff(results) {
        if (!results || !results.length) return '';
        const hasInput = results.some(function(r) { return r && r.ramp_tradeoff_input; });
        if (!hasInput) return '';

        const choices = rampTradeoffLandChoices(results);
        if (!choices.length) return '';
        const preferred = initialRampTradeoffIndex(results);
        let html = '<div class="ramp-tradeoff-section">';
        html += '<div class="ramp-tradeoff-header">';
        html += '<div><h2>Ramp Tradeoff</h2>';
        html += '<p class="rt-subtitle">Your deck\'s ramp approximated in Signet-equivalent units using the average number of draws measured during the simulation.</p></div>';
        html += '</div>';
        html += '<div class="lazy-panel-prompt">';
        html += '<span>Do you want to see the tradeoff of cutting or adding ramp?</span>';
        html += '<label class="rt-land-select-label">Current lands ';
        html += '<select id="rampTradeoffLandSelect">';
        for (const choice of choices) {
            const sel = choice.index === preferred ? ' selected' : '';
            html += '<option value="' + choice.index + '"' + sel + '>' + choice.land_count + '</option>';
        }
        html += '</select></label>';
        html += '<button type="button" class="btn btn-secondary btn-sm" id="rampTradeoffLoadBtn">Show Ramp Tradeoff</button>';
        html += '</div>';
        html += '<details class="ramp-tradeoff-help"><summary>How to read this</summary>';
        html += '<p>Each column is a generic two-mana Signet-equivalent variant of the same deck. The line chart shows surplus mana and stuck cards. The bars show how often the deck sees 0, 1, 2, or 3+ Signets by turn 5.</p>';
        html += '<p>Spend rate is mana spent as a share of mana available. A high spend rate at very low ramp is not a score to maximize. It can simply mean there was little mana to waste.</p>';
        html += '</details>';
        html += '<div id="rampTradeoffBody"></div>';
        html += '</div>';
        return html;
    }

    function renderRampTradeoffBody(result) {
        const rt = result && result.ramp_tradeoff;
        if (!rt) {
            return '<div class="rt-loading">Computing this land count when selected...</div>';
        }
        if (rt.suppressed) {
            return '<div class="rt-suppressed">' + escapeHtml(rt.reason || 'Ramp Tradeoff is not available for this deck.') + '</div>';
        }
        const variants = rt.variants || [];
        if (!variants.length) {
            return '<div class="rt-suppressed">Ramp Tradeoff is not available for this deck.</div>';
        }

        let html = '<div class="rt-summary-row">';
        html += '<span class="rt-stat"><span>Current Signets</span><strong>' + rt.current_rocks + '</strong></span>';
        html += '<span class="rt-stat"><span>Spendable spells</span><strong>' + fmt(rt.spendable_slots || 0, 0) + '</strong></span>';
        html += '<span class="rt-stat"><span>Trials / variant</span><strong>' + rt.n_trials + '</strong></span>';
        html += '<span class="rt-stat"><span>Early ramp</span><strong>Turn ' + rt.phase1_turn + '</strong></span>';
        html += '</div>';

        if (rt.callouts && rt.callouts.length) {
            html += '<div class="rt-callouts">';
            rt.callouts.forEach(function(callout) {
                html += '<p>' + escapeHtml(callout) + '</p>';
            });
            html += '</div>';
        }

        html += '<div class="ramp-tradeoff-grid">';
        html += '<div class="rt-chart-wrap"><canvas id="rampTradeoffMainChart"></canvas></div>';
        html += '<div class="rt-chart-wrap"><canvas id="rampTradeoffScenarioChart"></canvas></div>';
        html += '</div>';
        const cardsSeen = rt.cards_seen_by_phase1 != null ? fmt(rt.cards_seen_by_phase1, 0) : '?';
        html += '<p class="rt-note">Early ramp = Signets among about ' + cardsSeen + ' cards seen by turn ' + rt.phase1_turn + '. The same draw signature is held fixed across variants, so cantrip-heavy decks may make cutting ramp look safer than it really is.</p>';
        return html;
    }

    function renderRampTradeoffCharts(results) {
        const select = document.getElementById('rampTradeoffLandSelect');
        const index = select ? parseInt(select.value, 10) : initialRampTradeoffIndex(results);
        renderRampTradeoffChartsForResult(results[index]);
    }

    function renderRampTradeoffChartsForResult(result) {
        const rt = result && result.ramp_tradeoff;
        if (!rt || rt.suppressed || !rt.variants || !rt.variants.length) return;
        renderRampTradeoffMainChart(rt);
        renderRampTradeoffScenarioChart(rt);
    }

    function renderRampTradeoffMainChart(rt) {
        const canvas = document.getElementById('rampTradeoffMainChart');
        if (!canvas) return;
        const existing = Chart.getChart('rampTradeoffMainChart');
        if (existing) existing.destroy();

        const variants = rt.variants || [];
        const labels = variants.map(function(v) { return formatSignetVariantLabel(v.label); });
        const unspent = variants.map(function(v) { return v.unspent_mana; });
        const stuck = variants.map(function(v) { return v.stuck_cards; });
        const spendRates = variants.map(function(v) { return v.spend_rate; });

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Expected unspent mana',
                        data: unspent,
                        borderColor: '#2563eb',
                        backgroundColor: '#2563eb',
                        yAxisID: 'y',
                        borderWidth: 2,
                        pointRadius: 4,
                        tension: 0.2,
                    },
                    {
                        label: 'Expected stuck cards',
                        data: stuck,
                        borderColor: '#dc2626',
                        backgroundColor: '#dc2626',
                        yAxisID: 'y1',
                        borderWidth: 2,
                        pointRadius: 4,
                        tension: 0.2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: { display: true, text: 'Surplus mana vs. stuck cards by Signet-equivalent variant' },
                    tooltip: {
                        callbacks: {
                            footer: function(items) {
                                const idx = items[0] ? items[0].dataIndex : 0;
                                const v = variants[idx];
                                if (!v) return '';
                                return 'Signets: ' + v.R + '\nSpend rate: ' + Math.round((v.spend_rate || 0) * 100) + '%';
                            },
                        },
                    },
                },
                scales: {
                    x: { title: { display: true, text: 'Variant' } },
                    y: { type: 'linear', position: 'left', beginAtZero: true, title: { display: true, text: 'Unspent mana' } },
                    y1: { type: 'linear', position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: 'Stuck cards' } },
                },
            },
        });
    }

    function renderRampTradeoffScenarioChart(rt) {
        const canvas = document.getElementById('rampTradeoffScenarioChart');
        if (!canvas) return;
        const existing = Chart.getChart('rampTradeoffScenarioChart');
        if (existing) existing.destroy();

        const variants = rt.variants || [];
        const labels = variants.map(function(v) { return formatSignetVariantLabel(v.label); });
        const colors = ['#ef4444', '#f59e0b', '#22c55e', '#2563eb'];
        const names = ['0 Signets', '1 Signet', '2 Signets', '3+ Signets'];
        const datasets = ['0', '1', '2', '3'].map(function(bucket, i) {
            return {
                label: names[i],
                data: variants.map(function(v) { return (v.scenario_probs && v.scenario_probs[bucket] || 0) * 100; }),
                backgroundColor: colors[i],
                stack: 'early-ramp',
            };
        });

        new Chart(canvas, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: { display: true, text: 'Early ramp scenarios: Signets seen by turn ' + rt.phase1_turn },
                    tooltip: {
                        callbacks: {
                            label: function(item) {
                                return item.dataset.label + ': ' + item.parsed.y.toFixed(1) + '%';
                            },
                        },
                    },
                },
                scales: {
                    x: { stacked: true, title: { display: true, text: 'Variant' } },
                    y: { stacked: true, beginAtZero: true, max: 100, title: { display: true, text: 'Probability' } },
                },
            },
        });
    }

    function initRampTradeoff(results, options) {
        const section = document.querySelector('.ramp-tradeoff-section');
        if (!section) return;
        options = options || {};
        rampTradeoffContext = {
            results: results,
            worker: options.worker,
            deckJson: options.deckJson,
            config: options.config || {},
        };
        const select = document.getElementById('rampTradeoffLandSelect');
        const loadBtn = document.getElementById('rampTradeoffLoadBtn');
        function loadSelectedRampTradeoff() {
            if (!select) return;
            const idx = parseInt(select.value, 10);
            const result = results[idx];
            const body = document.getElementById('rampTradeoffBody');
            if (!body || !result) return;
            body.dataset.loaded = 'true';
            if (result.ramp_tradeoff) {
                body.innerHTML = renderRampTradeoffBody(result);
                renderRampTradeoffChartsForResult(result);
                return;
            }
            body.innerHTML = '<div class="rt-loading">Computing Ramp Tradeoff for ' + result.land_count + ' lands...</div>';
            if (!requestLazyRampTradeoff(idx)) {
                body.innerHTML = '<div class="rt-suppressed">Ramp Tradeoff for this land count is not available in this view.</div>';
            }
        }
        if (loadBtn) {
            loadBtn.addEventListener('click', loadSelectedRampTradeoff);
        }
        if (select) {
            select.addEventListener('change', function() {
                const idx = parseInt(select.value, 10);
                const result = results[idx];
                const body = document.getElementById('rampTradeoffBody');
                if (!body || !result) return;
                if (body.dataset.loaded !== 'true') return;
                if (result.ramp_tradeoff) {
                    body.innerHTML = renderRampTradeoffBody(result);
                    renderRampTradeoffChartsForResult(result);
                    return;
                }
                body.innerHTML = '<div class="rt-loading">Computing Ramp Tradeoff for ' + result.land_count + ' lands...</div>';
                if (!requestLazyRampTradeoff(idx)) {
                    body.innerHTML = '<div class="rt-suppressed">Ramp Tradeoff for this land count is not available in this view.</div>';
                }
            });
        }
    }

    function requestLazyRampTradeoff(index) {
        if (!rampTradeoffContext || !rampTradeoffContext.worker) return false;
        const result = rampTradeoffContext.results[index];
        if (!result || !result.ramp_tradeoff_input) return false;
        const requestId = 'rt-' + Date.now() + '-' + index;
        pendingRampTradeoff[requestId] = index;
        const config = Object.assign({}, rampTradeoffContext.config, {
            ramp_tradeoff_input: result.ramp_tradeoff_input,
        });
        rampTradeoffContext.worker.postMessage({
            type: 'ramp_tradeoff',
            requestId: requestId,
            resultIndex: index,
            deckJson: rampTradeoffContext.deckJson || '[]',
            signatureJson: JSON.stringify(result.mean_cumulative_draws_per_turn || []),
            configJson: JSON.stringify(config),
        });
        return true;
    }

    function handleRampTradeoffResult(msg) {
        if (!rampTradeoffContext) return;
        const index = msg.resultIndex != null ? msg.resultIndex : pendingRampTradeoff[msg.requestId];
        const result = rampTradeoffContext.results[index];
        if (!result) return;
        result.ramp_tradeoff = msg.data;
        delete pendingRampTradeoff[msg.requestId];
        const select = document.getElementById('rampTradeoffLandSelect');
        const currentIndex = select ? parseInt(select.value, 10) : initialRampTradeoffIndex(rampTradeoffContext.results);
        if (currentIndex === index) {
            const body = document.getElementById('rampTradeoffBody');
            if (body) {
                body.innerHTML = renderRampTradeoffBody(result);
                renderRampTradeoffChartsForResult(result);
            }
        }
    }

    function handleRampTradeoffError(msg) {
        delete pendingRampTradeoff[msg.requestId];
        const select = document.getElementById('rampTradeoffLandSelect');
        if (!select || parseInt(select.value, 10) !== msg.resultIndex) return;
        const body = document.getElementById('rampTradeoffBody');
        if (body) {
            body.innerHTML = '<div class="rt-suppressed">Ramp Tradeoff could not be computed: '
                + escapeHtml(msg.message || 'unknown error') + '</div>';
        }
    }

    function renderDeckScoreChart(results) {
        const r = results[results.length - 1];
        const score = r.deck_score;
        if (!score) return;

        const canvas = document.getElementById('deckScoreRadar');
        if (!canvas) return;

        const labels = ['Consistency', 'Acceleration', 'Snowball', 'Tuning', 'Efficiency', 'Reach'];
        const values = [score.consistency, score.acceleration, score.snowball, score.tuning, score.efficiency, score.reach];

        new Chart(canvas, {
            type: 'radar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'CASTER Score',
                    data: values,
                    backgroundColor: 'rgba(59, 130, 246, 0.2)',
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    pointBackgroundColor: '#3b82f6',
                    pointRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    r: {
                        min: 0,
                        max: 10,
                        ticks: { stepSize: 2, display: true },
                        pointLabels: { font: { size: 13, weight: 'bold' } },
                    }
                },
                plugins: {
                    legend: { display: false },
                }
            }
        });
    }

    function renderSummaryTable(results, isOptimization) {
        let html = '<h2>' + (isOptimization ? 'Optimization Results' : 'Summary Statistics') + '</h2>';
        if (isOptimization) {
            html += '<p class="hint">Ranked by optimization target. Top configurations evaluated with full simulation count.</p>';
        }
        html += `<details class="metric-descriptions">
            <summary>Metric Definitions</summary>
            <dl class="metric-list">
                <dt>Consistency</dt>
                <dd>Left-tail ratio: mean mana in the worst 25% of games divided by the overall mean (0-1 scale). 1.0 = perfectly consistent; lower values mean bad games are much worse than average. Based on the selected mana mode.</dd>
                <dt>Avg Spells</dt>
                <dd>Average number of spells cast per game.</dd>
                <dt>Mana Spent: V+D</dt>
                <dd>Total mana spent on value (no-effect) and draw spells. Ramp excluded because it pays for itself. Higher = more resources deployed.</dd>
                <dt>Mana Spent: Value / Draw / Ramp</dt>
                <dd>Mana breakdown by card type. Draw > ramp priority (cards with both count as draw).</dd>
                <dt>Mana Spent: All</dt>
                <dd>Total mana spent on all spells (value + draw + ramp).</dd>
                <dt>Hand Sum</dt>
                <dd>Sum of min(hand_size, 7) per turn. Measures card availability across the game.</dd>
                <dt>Bad Turns</dt>
                <dd>Average turns where no spells were cast and the deck wasn&rsquo;t empty. Lower = better.</dd>
                <dt>Mid Turns</dt>
                <dd>Average turns where fewer than 2 spells were cast, mana spent was below the turn number, and the deck wasn&rsquo;t empty. Lower = better.</dd>
                <dt>Avg Lands / Avg Mulls</dt>
                <dd>Average lands played and mulligans taken per game.</dd>
                <dt>Avg Draws</dt>
                <dd>Average cards drawn per game.</dd>
                <dt>Mana Percentiles (25th / 50th / 75th)</dt>
                <dd>Percentiles of mana spent (based on selected mana mode) showing distribution spread.</dd>
            </dl>
        </details>`;
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
        if (isOptimization) html += '<th rowspan="2">Rank</th><th rowspan="2">Configuration</th>';
        html += '<th rowspan="2">Lands</th><th rowspan="2">Consistency</th><th rowspan="2">Avg Spells</th>';
        html += '<th colspan="5">Mana Spent <span class="mana-view-toggle" data-current="bottom_25">';
        html += '<button class="mana-view-btn active" data-view="bottom_25" title="Average mana in worst 25% of games">Floor</button>';
        html += '<button class="mana-view-btn" data-view="mean" title="Average mana across all games">Mean</button>';
        html += '<button class="mana-view-btn" data-view="top_25" title="Average mana in best 25% of games">Ceiling</button>';
        html += '</span></th>';
        html += '<th rowspan="2">Hand Sum</th><th rowspan="2">Bad Turns</th>';
        html += '<th rowspan="2">Mid Turns</th><th rowspan="2">Avg Lands</th><th rowspan="2">Avg Mulls</th>';
        html += '<th rowspan="2">Avg Draws</th>';
        html += '<th colspan="3">Mana Percentiles</th></tr><tr>';
        html += '<th>Value</th><th>Draw</th><th>Ramp</th><th>V+D</th><th>All</th>';
        html += '<th>25th</th><th>50th</th><th>75th</th></tr></thead><tbody>';

        const colCount = isOptimization ? 19 : 17;
        for (let i = 0; i < results.length; i++) {
            const r = results[i];
            const isBaselineRef = isOptimization && r.opt_baseline_rank != null;

            // Insert separator before the baseline reference row
            if (isBaselineRef) {
                html += '<tr class="baseline-separator"><td colspan="' + colCount + '"></td></tr>';
            }

            const conMargin = r.ci_consistency ? (r.ci_consistency[1] - r.ci_consistency[0]) / 2 : 0;
            let rowStyle = '';
            if (isOptimization && i === 0) rowStyle = ' style="font-weight:bold; background:#e8f5e9;"';
            if (isBaselineRef) rowStyle = ' style="opacity:0.75; border-top:2px dashed #94a3b8;"';
            html += '<tr' + rowStyle + '>';
            if (isOptimization) {
                const rank = isBaselineRef ? r.opt_baseline_rank : (i + 1);
                html += '<td>' + rank + '</td>';
                const sourceBadge = r.opt_source ? ' <span class="source-badge source-' + r.opt_source + '">' + r.opt_source + '</span>' : '';
                html += '<td style="text-align:left">' + formatConfig(r.opt_config || 'Base deck') + sourceBadge + '</td>';
            }
            html += '<td>' + r.land_count + '</td>';
            html += '<td>' + fmt(r.consistency, 3) + ' <small>&plusmn;' + fmt(conMargin, 4) + '</small></td>';
            html += '<td>' + fmt(r.mean_spells_cast ?? 0, 2) + '</td>';
            var qm = r.quartile_mana || {};
            var bot = qm.bottom_25 || {}; var mn = qm.mean || {}; var top = qm.top_25 || {};
            var manaFields = ['value', 'draw', 'ramp', 'vd', 'all'];
            var ciFields = [r.ci_mana_value ?? 0, r.ci_mana_draw ?? 0, r.ci_mana_ramp ?? 0, r.ci_mana ?? 0, r.ci_mana_total ?? 0];
            for (var mi = 0; mi < manaFields.length; mi++) {
                var fld = manaFields[mi];
                var bv = bot[fld] ?? 0, mv = mn[fld] ?? 0, tv = top[fld] ?? 0;
                html += '<td class="mana-cell" data-bot="' + fmt(bv, 2) + '" data-mean="' + fmt(mv, 2) + '" data-top="' + fmt(tv, 2)
                    + '" data-ci="' + fmt(ciFields[mi], 2) + '">'
                    + fmt(bv, 2) + ' <small>&plusmn;' + fmt(ciFields[mi], 2) + '</small></td>';
            }
            html += '<td>' + fmt(r.mean_hand_sum ?? 0, 1) + '</td>';
            html += '<td>' + fmt(r.mean_bad_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mid_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_lands, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mulls, 2) + '</td>';
            html += '<td>' + fmt(r.mean_draws ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.percentile_25, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_50, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_75, 1) + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        return html;
    }

    const ORDINALS = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th'];
    function ordinal(k) { return ORDINALS[k] || (k + 'th'); }

    function renderCardPerformance(results) {
        const cp = results[0].card_performance;
        if (!cp || !cp.high_performing) return '';

        let html = '<h2>Card Performance</h2>';
        html += '<details class="card-perf-help">'
            + '<summary>How to read this table</summary>'
            + '<p>Spells with the same mana cost and same simulator-relevant effects are pooled into a single archetype. The example shown is one card from the pool.</p>'
            + '<ul class="card-perf-help-list">'
            + '<li>Impact: average mana spent in games where you drew at least one copy minus games where you did not.</li>'
            + '<li>Each extra copy: marginal value of the 1st, 2nd, and 3rd copy. A faded "-" means the confidence interval overlaps zero. Rare ordinals are hidden.</li>'
            + '<li>Recommendation: add more, enough, cut copies, or not enough data.</li>'
            + '<li><sup class="always-drawn">∑</sup> means the spell appeared in nearly every game, so there is no "drew none" group.</li>'
            + '</ul>'
            + '<p>Lands are excluded. MDFCs stay because their spell face matters.</p>'
            + '</details>';
        const supplementalSuffix = cp.supplemental_games
            ? '. Includes ' + cp.supplemental_games + ' supplemental games for marginal precision'
            : '';
        html += '<p class="card-perf-summary">Impact of drawing each spell on average mana spent across '
            + cp.total_games + ' games' + supplementalSuffix + '.</p>';
        html += '<div class="card-perf-grid">';

        function renderMarginals(card) {
            if (!card.marginals || !card.marginals.length) return '';
            const parts = card.marginals.map(m => {
                const ord = ordinal(m.k);
                if (m.noise) {
                    const tip = ord + ' copy: 90% CI overlaps zero, so the effect is too small to distinguish from chance. '
                        + m.n_curr + ' games drew exactly ' + m.k + '.';
                    return '<span class="marginal noise" data-tip="' + escapeHtml(tip) + '">'
                        + ord + ': -</span>';
                }
                const cls = m.effect > 0 ? 'pos' : 'neg';
                const sign = m.effect >= 0 ? '+' : '';
                const tip = 'Drawing the ' + ord + ' copy changes total mana spent by '
                    + sign + fmt(m.effect, 2) + ' on average. 90% CI ±' + fmt(m.ci, 2)
                    + ', based on ' + m.n_curr + ' games.';
                return '<span class="marginal ' + cls + '" data-tip="' + escapeHtml(tip) + '">'
                    + ord + ': ' + sign + fmt(m.effect, 2) + '</span>';
            });
            return '<div class="marginals">' + parts.join('') + '</div>';
        }

        function renderBadge(card) {
            const sat = card.saturation || {};
            if (sat.badge === 'scaling') {
                return '<span class="sat-badge sat-scaling" data-tip="Every extra copy you draw is still adding measurable mana. More copies would likely help.">↑ Add more</span>';
            }
            if (sat.badge === 'saturated') {
                const k = sat.saturates_at;
                const range = sat.copy_range;
                const copies = card.copies || 1;
                if (range) {
                    const rangeLabel = range.min_copies === range.max_copies
                        ? range.min_copies + ' copies'
                        : range.min_copies + '-' + range.max_copies + ' copies';
                    let statusNote;
                    if (range.status === 'high') {
                        statusNote = 'Currently ' + copies + '. Consider trimming toward ' + range.max_copies + '.';
                    } else if (range.status === 'low') {
                        statusNote = 'Currently ' + copies + '. Could add more, up to about ' + range.max_copies + '.';
                    } else {
                        statusNote = 'Currently ' + copies + '. Looks right.';
                    }
                    const tip = 'Drawing more than ' + k + ' copy in the same game stops adding measurable mana. '
                        + 'Hypergeometric range where you draw it often enough but rarely waste extras: '
                        + rangeLabel + '. ' + statusNote;
                    const cls = range.status === 'high'
                        ? 'sat-saturated sat-trim'
                        : range.status === 'low' ? 'sat-saturated sat-room' : 'sat-saturated';
                    return '<span class="sat-badge ' + cls + '" data-tip="' + escapeHtml(tip) + '">≈ Sweet spot: ' + rangeLabel + '</span>';
                }
                const tip = 'Drawing more than ' + k + ' copy in the same game does not add measurable mana. '
                    + 'Currently ' + copies + ' copies. Only consider cutting if you frequently draw '
                    + (k + 1) + '+.';
                return '<span class="sat-badge sat-saturated" data-tip="' + escapeHtml(tip) + '">≈ Enough drawn at ' + k + '</span>';
            }
            if (sat.badge === 'crowding') {
                return '<span class="sat-badge sat-crowding" data-tip="Drawing extra copies actually hurts (they crowd your hand or compete for mana). Consider running fewer.">↓ Cut copies</span>';
            }
            if (sat.badge === 'unclear') {
                return '<span class="sat-badge sat-unclear" data-tip="Not enough games drew this spell at varying counts to give a confident verdict. Try running more simulations.">? Need more data</span>';
            }
            return '';
        }

        function renderRow(card, i, scoreClass) {
            const label = escapeHtml(card.label || card.name);
            const copies = card.copies || 1;
            const tip = card.always_drawn
                ? 'Drawn in nearly every game, so there is no "didn\'t draw it" group to compare against. Score shown is the sum of the per-copy effects that were statistically significant.'
                : 'Average mana spent in games that drew this spell (' + fmt(card.mean_with, 2)
                    + ") minus games that didn't (" + fmt(card.mean_without, 2) + ').';
            const marker = card.always_drawn ? '<sup class="always-drawn">∑</sup>' : '';
            let row = '<tr><td>' + (i + 1) + '</td>';
            row += '<td style="text-align:left"><div>' + label + '</div>';
            row += '<small>e.g. ' + cardLink(card.name) + '</small></td>';
            row += '<td>' + copies + '</td>';
            row += '<td>' + escapeHtml(card.cost) + '</td>';
            row += '<td class="' + scoreClass + '" title="' + escapeHtml(tip) + '">' + (card.score >= 0 ? '+' : '') + fmt(card.score, 2) + marker + '</td>';
            row += '<td style="text-align:left">' + renderMarginals(card) + '</td>';
            row += '<td>' + renderBadge(card) + '</td></tr>';
            return row;
        }

        const headerCells = '<th>#</th>'
            + '<th>Spell</th>'
            + '<th title="How many copies of this spell or simulator-equivalent variants are in the deck.">Copies</th>'
            + '<th title="Average mana actually paid when this spell was cast across all simulated games.">Avg cost</th>'
            + '<th title="Average mana spent in games that drew at least one copy minus games that drew none. Positive = the deck performs better with this spell in hand.">Impact</th>'
            + '<th data-tip="Per-copy effect: how much more or less mana the deck spends when you draw the 1st, 2nd, or 3rd copy compared to having one fewer. Hover any pill for details.">Each extra copy <span class="help-icon" aria-hidden="true">?</span></th>'
            + '<th data-tip="Plain-English verdict on whether to add more copies, you have enough, cut copies, or there isn\'t enough data yet.">Recommendation <span class="help-icon" aria-hidden="true">?</span></th>';

        const high = cp.high_performing || [];
        const low = cp.low_performing || [];
        const cardKey = (c) => (c.label || c.name) + '|' + (c.copies || 1);
        const highKeys = new Set(high.map(cardKey));
        const lowKeys = new Set(low.map(cardKey));
        const overlap = [...highKeys].some(k => lowKeys.has(k));
        // Below ~12 distinct pools the server's high/low split degenerates into
        // showing the same rows in both tables. Collapse to a single ranked table.
        const collapsed = overlap || high.length === 0 || low.length === 0;

        if (collapsed) {
            const seen = new Set();
            const merged = [];
            high.concat(low).forEach(c => {
                const k = cardKey(c);
                if (!seen.has(k)) { seen.add(k); merged.push(c); }
            });
            merged.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
            html += '<div><h3>Ranked by impact</h3><div class="table-wrap"><table class="stats-table">';
            html += '<thead><tr>' + headerCells + '</tr></thead><tbody>';
            merged.forEach((card, i) => {
                const cls = (card.score ?? 0) >= 0 ? 'score-positive' : 'score-negative';
                html += renderRow(card, i, cls);
            });
            html += '</tbody></table></div></div></div>';
            return html;
        }

        html += '<div><h3>Top Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr>' + headerCells + '</tr></thead><tbody>';
        high.forEach((card, i) => {
            html += renderRow(card, i, 'score-positive');
        });
        html += '</tbody></table></div></div>';

        html += '<div><h3>Low Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr>' + headerCells + '</tr></thead><tbody>';
        low.forEach((card, i) => {
            html += renderRow(card, i, 'score-negative');
        });
        html += '</tbody></table></div></div></div>';
        return html;
    }

    function renderChartCanvases() {
        return `<h2>Charts</h2>
        <div class="charts-grid">
            <div class="chart-container"><canvas id="manaChart"></canvas></div>
            <div class="chart-container"><canvas id="consistencyChart"></canvas></div>
        </div>`;
    }

    function renderReplayHTML(results) {
        if (!results[0].replay_data || !results[0].replay_data.top
            || results[0].replay_data.top.length === 0) return '';

        return `<h2>Game Replays</h2>
        <div class="replay-container" id="replay-viewer">
            <div class="replay-tabs" id="replay-tabs">
                <button class="replay-tab active" data-quantile="top">Top Quartile</button>
                <button class="replay-tab" data-quantile="mid">Mid</button>
                <button class="replay-tab" data-quantile="low">Low Quartile</button>
            </div>
            <div class="replay-games" id="replay-games"></div>
            <div class="replay-info" id="replay-info"></div>
            <div class="replay-nav" id="replay-nav">
                <button id="replay-prev">&lt; Prev</button>
                <span class="turn-counter" id="replay-turn-counter"></span>
                <button id="replay-next">Next &gt;</button>
            </div>
            <div id="replay-content">
                <div class="replay-section">
                    <h4>Hand (before draw):</h4>
                    <div class="replay-card-list" id="replay-hand-before"></div>
                </div>
                <div class="replay-section">
                    <h4>Played this turn:</h4>
                    <div class="replay-card-list" id="replay-played"></div>
                </div>
                <div class="replay-section">
                    <h4>Board State:</h4>
                    <div class="replay-card-list" id="replay-board"></div>
                </div>
            </div>
            <p class="replay-disclaimer">
                Mana model: every land is treated like a basic Wastes. One untapped colorless mana.
                Color requirements, tapped lands, and fetches are not simulated.
            </p>
        </div>`;
    }

    // -- Chart rendering --

    function renderCharts(data) {
        const labels = data.map(d => d.land_count);

        // Destroy existing charts
        ['manaChart', 'consistencyChart'].forEach(id => {
            const existing = Chart.getChart(id);
            if (existing) existing.destroy();
        });

        // Mana EV
        new Chart(document.getElementById('manaChart'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {label: 'Mean Mana', data: data.map(d => d.mean_mana),
                     borderColor: '#2563eb', backgroundColor: '#2563eb', borderWidth: 2, fill: false},
                    {label: '75th Percentile', data: data.map(d => d.percentile_75),
                     borderColor: 'rgba(37, 99, 235, 0.3)', backgroundColor: 'rgba(37, 99, 235, 0.1)',
                     borderWidth: 1, fill: '+1'},
                    {label: '50th Percentile', data: data.map(d => d.percentile_50),
                     borderColor: 'rgba(37, 99, 235, 0.5)', backgroundColor: 'rgba(37, 99, 235, 0.1)',
                     borderWidth: 1, fill: false, borderDash: [5, 5]},
                    {label: '25th Percentile', data: data.map(d => d.percentile_25),
                     borderColor: 'rgba(37, 99, 235, 0.3)', backgroundColor: 'rgba(37, 99, 235, 0.1)',
                     borderWidth: 1, fill: '-1'},
                ]
            },
            options: {
                responsive: true,
                plugins: {title: {display: true, text: 'Mana EV by Land Count'}},
                scales: {
                    x: {title: {display: true, text: 'Land Count'}},
                    y: {title: {display: true, text: 'Total Mana Spent'}}
                }
            }
        });

        // Consistency
        new Chart(document.getElementById('consistencyChart'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Consistency',
                    data: data.map(d => d.consistency),
                    borderColor: '#16a34a', backgroundColor: '#16a34a',
                    borderWidth: 2, fill: false,
                }]
            },
            options: {
                responsive: true,
                plugins: {title: {display: true, text: 'Consistency Score by Land Count'}},
                scales: {
                    x: {title: {display: true, text: 'Land Count'}},
                    y: {title: {display: true, text: 'Consistency'}, min: 0, max: 1.2}
                }
            }
        });
    }

    // -- Replay viewer --

    function initReplayViewer(data) {
        const viewer = document.getElementById('replay-viewer');
        if (!viewer) return;

        const replayData = data[0].replay_data;
        if (!replayData || !replayData.top || replayData.top.length === 0) return;

        let currentQuantile = 'top';
        let currentGame = 0;
        let currentTurn = 0;

        function renderGameButtons() {
            const games = replayData[currentQuantile] || [];
            const container = document.getElementById('replay-games');
            container.innerHTML = '';
            for (let i = 0; i < games.length; i++) {
                const btn = document.createElement('button');
                btn.className = 'replay-game-btn' + (i === currentGame ? ' active' : '');
                btn.textContent = i + 1;
                btn.addEventListener('click', function() {
                    currentGame = i;
                    currentTurn = 0;
                    renderReplay();
                });
                container.appendChild(btn);
            }
        }

        function renderReplay() {
            const games = replayData[currentQuantile] || [];
            if (games.length === 0) {
                document.getElementById('replay-info').textContent = 'No games in this bucket.';
                document.getElementById('replay-turn-counter').textContent = '';
                document.getElementById('replay-hand-before').innerHTML = '';
                document.getElementById('replay-played').innerHTML = '';
                document.getElementById('replay-board').innerHTML = '';
                renderGameButtons();
                return;
            }

            const game = games[currentGame];
            const turn = game.turns[currentTurn];

            document.querySelectorAll('.replay-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.quantile === currentQuantile);
            });

            renderGameButtons();

            document.getElementById('replay-info').innerHTML =
                '<strong>Mana:</strong> ' + game.total_mana
                + ' &nbsp;|&nbsp; <strong>Mulligans:</strong> ' + game.mulligans
                + ' &nbsp;|&nbsp; <strong>Starting hand:</strong> '
                + game.starting_hand.map(cardLink).join(', ');

            document.getElementById('replay-turn-counter').textContent =
                'Turn ' + turn.turn + ' of ' + game.turns.length;
            document.getElementById('replay-prev').disabled = currentTurn === 0;
            document.getElementById('replay-next').disabled = currentTurn === game.turns.length - 1;

            document.getElementById('replay-hand-before').innerHTML =
                turn.hand_before_draw.length > 0
                    ? turn.hand_before_draw.map(cardLink).join(', ')
                    : '<em>Empty</em>';

            const playedHtml = turn.played.map(function(c) {
                const cls = 'replay-played-card' + (c.is_land ? ' is-land' : '');
                const detail = c.is_land ? '(land)' : '(' + escapeHtml(c.cost) + ', ' + c.mana_spent + ' mana)';
                return '<span class="' + cls + '">' + cardLink(c.name) + ' ' + detail + '</span>';
            }).join(' ');
            document.getElementById('replay-played').innerHTML = playedHtml || '<em>Nothing played</em>';

            const boardParts = [];
            boardParts.push('<strong>Mana spent:</strong> ' + turn.mana_spent_this_turn
                + ' &nbsp;|&nbsp; <strong>Total production:</strong> ' + turn.total_mana_production);
            boardParts.push('<br><strong>Battlefield:</strong> '
                + (turn.battlefield.length > 0 ? turn.battlefield.map(cardLink).join(', ') : '<em>Empty</em>'));
            boardParts.push('<br><strong>Lands:</strong> '
                + (turn.lands.length > 0 ? turn.lands.map(cardLink).join(', ') : '<em>None</em>'));
            boardParts.push('<br><strong>Hand:</strong> '
                + (turn.hand_after.length > 0 ? turn.hand_after.map(cardLink).join(', ') : '<em>Empty</em>'));
            if (turn.graveyard.length > 0) {
                boardParts.push('<br><strong>Graveyard:</strong> ' + turn.graveyard.map(cardLink).join(', '));
            }
            document.getElementById('replay-board').innerHTML = boardParts.join('');

            rebindTooltips();
        }

        document.querySelectorAll('.replay-tab').forEach(tab => {
            tab.addEventListener('click', function() {
                currentQuantile = this.dataset.quantile;
                currentGame = 0;
                currentTurn = 0;
                renderReplay();
            });
        });

        document.getElementById('replay-prev').addEventListener('click', function() {
            if (currentTurn > 0) { currentTurn--; renderReplay(); }
        });
        document.getElementById('replay-next').addEventListener('click', function() {
            const games = replayData[currentQuantile] || [];
            if (games.length > 0 && currentTurn < games[currentGame].turns.length - 1) {
                currentTurn++;
                renderReplay();
            }
        });

        renderReplay();
    }

    // -- Feature Analysis --

    /**
     * Render recommendation text, inserting a Scryfall hover link for the
     * example card when present (reuses the existing card-link tooltip system).
     */
    function renderRecText(r) {
        if (!r.example_card) {
            return escapeHtml(r.recommendation);
        }
        var name = r.example_card.name;
        var text = r.recommendation;
        var idx = text.indexOf(name);
        if (idx === -1) {
            return escapeHtml(text);
        }
        var before = text.substring(0, idx);
        var after = text.substring(idx + name.length);
        return escapeHtml(before) + cardLink(name) + escapeHtml(after);
    }

    function renderFeatureAnalysis(results) {
        const analysis = results[0] && results[0].feature_analysis;
        if (!analysis || !analysis.recommendations || analysis.recommendations.length === 0) {
            return '';
        }

        let html = '<div class="feature-analysis-section">';
        html += '<h2>Recommended Changes</h2>';
        html += '<p class="hint">Based on analysis of ' + analysis.n_configs
            + ' configurations evaluated during optimization.</p>';

        // Synthesized recommendations
        const recs = analysis.recommendations;
        const positiveRecs = recs.filter(function(r) { return r.impact > 0; });
        const negativeRecs = recs.filter(function(r) { return r.impact < 0; });

        if (positiveRecs.length > 0) {
            html += '<div class="recommendations-list">';
            html += '<h3>Changes that improve results</h3>';
            html += '<ul class="rec-list">';
            for (let i = 0; i < Math.min(positiveRecs.length, 8); i++) {
                const r = positiveRecs[i];
                const badge = r.confidence === 'high' ? 'rec-badge-high'
                    : r.confidence === 'medium' ? 'rec-badge-med' : 'rec-badge-low';
                html += '<li class="rec-item rec-positive">';
                html += '<span class="rec-badge ' + badge + '">' + r.confidence + '</span> ';
                html += '<strong>' + escapeHtml(r.label) + '</strong>: ';
                html += renderRecText(r);
                html += ' <span class="rec-delta">(';
                html += r.impact > 0 ? '+' : '';
                html += fmt(r.impact, 4) + ')</span>';
                html += '</li>';
            }
            html += '</ul></div>';
        }

        if (negativeRecs.length > 0) {
            html += '<div class="recommendations-list">';
            html += '<h3>Changes that hurt results</h3>';
            html += '<ul class="rec-list">';
            for (let i = 0; i < Math.min(negativeRecs.length, 5); i++) {
                const r = negativeRecs[i];
                const badge = r.confidence === 'high' ? 'rec-badge-high'
                    : r.confidence === 'medium' ? 'rec-badge-med' : 'rec-badge-low';
                html += '<li class="rec-item rec-negative">';
                html += '<span class="rec-badge ' + badge + '">' + r.confidence + '</span> ';
                html += '<strong>' + escapeHtml(r.label) + '</strong>: ';
                html += renderRecText(r);
                html += ' <span class="rec-delta">(';
                html += r.impact > 0 ? '+' : '';
                html += fmt(r.impact, 4) + ')</span>';
                html += '</li>';
            }
            html += '</ul></div>';
        }

        // Advanced statistics dropdown
        html += '<details class="advanced-stats">';
        html += '<summary>Advanced Statistics</summary>';

        // Regression summary
        const reg = analysis.regression;
        if (reg) {
            html += '<div class="stats-subsection">';
            html += '<h4>Regression Analysis '
                + (reg.weighted ? '(Weighted Least Squares)' : '(OLS)')
                + '</h4>';
            html += '<p>R&sup2; = ' + fmt(reg.r_squared, 4)
                + '. Model explains ' + fmt(reg.r_squared * 100, 1)
                + '% of score variance.</p>';
            html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
            html += '<th>Feature</th><th>Coefficient</th><th>Std Beta</th>';
            html += '</tr></thead><tbody>';
            for (let i = 0; i < reg.coefficients.length; i++) {
                const c = reg.coefficients[i];
                const cls = c.coefficient > 0 ? 'score-positive' : c.coefficient < 0 ? 'score-negative' : '';
                html += '<tr>';
                html += '<td style="text-align:left">' + escapeHtml(c.label || c.feature) + '</td>';
                html += '<td class="' + cls + '">' + (c.coefficient >= 0 ? '+' : '') + fmt(c.coefficient, 4) + '</td>';
                html += '<td>' + fmt(c.std_beta, 4) + '</td>';
                html += '</tr>';
            }
            html += '</tbody></table></div></div>';
        }

        // Marginal impact table
        const marginal = analysis.marginal_impact;
        if (marginal && marginal.length > 0) {
            html += '<div class="stats-subsection">';
            html += '<h4>Marginal Feature Impact</h4>';
            html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
            html += '<th>Feature</th><th>Delta</th><th>Mean With</th><th>Mean Without</th><th>Count</th>';
            html += '</tr></thead><tbody>';
            for (let i = 0; i < marginal.length; i++) {
                const m = marginal[i];
                const cls = m.delta > 0 ? 'score-positive' : m.delta < 0 ? 'score-negative' : '';
                html += '<tr>';
                html += '<td style="text-align:left">' + escapeHtml(m.label) + '</td>';
                html += '<td class="' + cls + '">' + (m.delta >= 0 ? '+' : '') + fmt(m.delta, 4) + '</td>';
                html += '<td>' + fmt(m.mean_with, 4) + '</td>';
                html += '<td>' + fmt(m.mean_without, 4) + '</td>';
                html += '<td>' + m.count + '</td>';
                html += '</tr>';
            }
            html += '</tbody></table></div></div>';
        }

        html += '</details>';
        html += '</div>';
        return html;
    }

    // -- Mana view toggle --

    function initManaViewToggle(container) {
        container.querySelectorAll('.mana-view-toggle').forEach(function(toggle) {
            toggle.querySelectorAll('.mana-view-btn').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var view = this.dataset.view;
                    toggle.dataset.current = view;
                    toggle.querySelectorAll('.mana-view-btn').forEach(function(b) {
                        b.classList.toggle('active', b.dataset.view === view);
                    });
                    var table = toggle.closest('table');
                    var dataKey = view === 'bottom_25' ? 'bot' : view === 'top_25' ? 'top' : 'mean';
                    table.querySelectorAll('.mana-cell').forEach(function(cell) {
                        var val = cell.dataset[dataKey];
                        var ci = cell.dataset.ci;
                        cell.innerHTML = val + ' <small>&plusmn;' + ci + '</small>';
                    });
                });
            });
        });
    }

    // -- Public API --

    /**
     * Render simulation results into a container element.
     *
     * @param {HTMLElement} container - Target element to render into
     * @param {Array} results - Array of result dicts (from result_to_dict)
     * @param {string} deckName - Deck name for the title
     */
    function render(container, results, deckName, options) {
        const isOptimization = results.length > 0 && results[0].opt_config !== undefined;

        let html = '<div class="results-content">';
        html += '<h1>Results: ' + escapeHtml(deckName) + '</h1>';

        html += renderDeckScore(results);
        // Render curve_value panel for both simulation and optimization paths.
        // For optimization runs the panel reflects the baseline (input) deck
        // composition, since per-config curve_value would be heavyweight.
        html += renderCurveValue(results);
        html += renderRampTradeoff(results);
        if (isOptimization) {
            html += renderFeatureAnalysis(results);
        }
        html += renderSummaryTable(results, isOptimization);
        html += renderCardPerformance(results);
        if (!isOptimization) {
            html += renderChartCanvases();
        }
        html += renderReplayHTML(results);
        html += '</div>';

        container.innerHTML = html;

        // Render interactive components after DOM is updated
        renderDeckScoreChart(results);
        wireCasterShare(results, deckName);
        renderCurveValueTurnSpendChart(results);
        renderCurveValueChart(results);
        initCurveValueLazyPanels(results, options || {});
        initRampTradeoff(results, options || {});
        if (!isOptimization) {
            renderCharts(results);
        }
        initManaViewToggle(container);
        initReplayViewer(results);
        rebindTooltips();
    }

    return {
        render,
        rebindTooltips,
        renderCharts,
        initReplayViewer,
        handleRampTradeoffResult,
        handleRampTradeoffError,
        handleTurnStructureVariantResult,
        handleTurnStructureVariantError,
    };
})();
// Make this idempotent across document.write() reloads (see top of file).
if (typeof window !== 'undefined') { window.ClientResults = ClientResults; }

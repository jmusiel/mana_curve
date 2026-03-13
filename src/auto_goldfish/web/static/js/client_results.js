/**
 * Client-side results renderer.
 *
 * Renders simulation results from JSON into HTML, replicating the
 * server-side results_content.html template. Used when simulations
 * run client-side via Pyodide.
 */

const ClientResults = (function() {
    'use strict';

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

    function cardLink(name) {
        return '<a class="card-link" data-card-name="' + escapeHtml(name)
            + '" href="https://scryfall.com/search?exact='
            + encodeURIComponent(name) + '" target="_blank">' + escapeHtml(name) + '</a>';
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

    function renderSummaryTable(results, isOptimization) {
        let html = '<h2>' + (isOptimization ? 'Optimization Results' : 'Summary Statistics') + '</h2>';
        if (isOptimization) {
            html += '<p class="hint">Ranked by optimization target. Top configurations evaluated with full simulation count.</p>';
        }
        html += `<details class="metric-descriptions">
            <summary>Metric Definitions</summary>
            <dl class="metric-list">
                <dt>Mana Spent: V+D</dt>
                <dd>Total mana spent on value (no-effect) and draw spells. Ramp excluded because it pays for itself. Higher = more resources deployed.</dd>
                <dt>Mana Spent: Value / Draw / Ramp</dt>
                <dd>Mana breakdown by card type. Draw > ramp priority (cards with both count as draw).</dd>
                <dt>Mana Spent: All</dt>
                <dd>Total mana spent on all spells (value + draw + ramp).</dd>
                <dt>Hand Sum</dt>
                <dd>Sum of min(hand_size, 7) per turn. Measures card availability across the game.</dd>
                <dt>Consistency</dt>
                <dd>How reliably the deck avoids low-mana games (0&ndash;1.2 scale). 1.0 = perfectly consistent. Computed from cumulative mana distribution based on selected mana mode.</dd>
                <dt>Bad Turns</dt>
                <dd>Average turns where no spells were cast and the deck wasn&rsquo;t empty. Lower = better.</dd>
                <dt>Mid Turns</dt>
                <dd>Average turns with fewer than 2 spells and mana spent below the turn number. Lower = better.</dd>
                <dt>Avg Lands / Avg Mulls</dt>
                <dd>Average lands played and mulligans taken per game.</dd>
                <dt>Avg Draws / Avg Spells</dt>
                <dd>Average cards drawn and spells cast per game.</dd>
                <dt>Mana Percentiles (25th / 50th / 75th)</dt>
                <dd>Percentiles of mana spent (based on selected mana mode) showing distribution spread.</dd>
            </dl>
        </details>`;
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
        if (isOptimization) html += '<th rowspan="2">Rank</th><th rowspan="2">Configuration</th>';
        html += '<th rowspan="2">Lands</th><th colspan="5">Mana Spent</th>';
        html += '<th rowspan="2">Hand Sum</th><th rowspan="2">Consistency</th><th rowspan="2">Bad Turns</th>';
        html += '<th rowspan="2">Mid Turns</th><th rowspan="2">Avg Lands</th><th rowspan="2">Avg Mulls</th>';
        html += '<th rowspan="2">Avg Draws</th><th rowspan="2">Avg Spells</th>';
        html += '<th colspan="3">Mana Percentiles</th></tr><tr>';
        html += '<th>Value</th><th>Draw</th><th>Ramp</th><th>V+D</th><th>All</th>';
        html += '<th>25th</th><th>50th</th><th>75th</th></tr></thead><tbody>';

        for (let i = 0; i < results.length; i++) {
            const r = results[i];
            const conMargin = r.ci_consistency ? (r.ci_consistency[1] - r.ci_consistency[0]) / 2 : 0;
            html += '<tr' + (isOptimization && i === 0 ? ' style="font-weight:bold; background:#e8f5e9;"' : '') + '>';
            if (isOptimization) {
                html += '<td>' + (i + 1) + '</td>';
                html += '<td style="text-align:left">' + formatConfig(r.opt_config || 'Base deck') + '</td>';
            }
            html += '<td>' + r.land_count + '</td>';
            html += '<td>' + fmt(r.mean_mana_value ?? 0, 2) + ' <small>&plusmn;' + fmt(r.ci_mana_value ?? 0, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_mana_draw ?? 0, 2) + ' <small>&plusmn;' + fmt(r.ci_mana_draw ?? 0, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_mana_ramp ?? 0, 2) + ' <small>&plusmn;' + fmt(r.ci_mana_ramp ?? 0, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_mana, 2) + ' <small>&plusmn;' + fmt(r.ci_mana ?? 0, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_mana_total ?? 0, 2) + ' <small>&plusmn;' + fmt(r.ci_mana_total ?? 0, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_hand_sum ?? 0, 1) + '</td>';
            html += '<td>' + fmt(r.consistency, 3) + ' <small>&plusmn;' + fmt(conMargin, 4) + '</small></td>';
            html += '<td>' + fmt(r.mean_bad_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mid_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_lands, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mulls, 2) + '</td>';
            html += '<td>' + fmt(r.mean_draws ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.mean_spells_cast ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.percentile_25, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_50, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_75, 1) + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        return html;
    }

    function renderCardPerformance(results) {
        const cp = results[0].card_performance;
        if (!cp || !cp.high_performing) return '';

        let html = '<h2>Card Performance</h2>';
        html += '<p class="card-perf-summary">Impact of drawing each card on average mana spent across '
            + cp.total_games + ' games.</p>';
        html += '<div class="card-perf-grid">';

        // High performers
        html += '<div><h3>Top Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr><th>#</th><th>Card</th><th>Cost</th><th>Effects</th>';
        html += '<th>Avg With</th><th>Avg Without</th><th>Impact</th></tr></thead><tbody>';
        cp.high_performing.forEach((card, i) => {
            html += '<tr><td>' + (i + 1) + '</td>';
            html += '<td style="text-align:left">' + cardLink(card.name) + '</td>';
            html += '<td>' + escapeHtml(card.cost) + '</td>';
            html += '<td style="text-align:left">' + escapeHtml(card.effects) + '</td>';
            html += '<td>' + fmt(card.mean_with, 2) + '</td>';
            html += '<td>' + fmt(card.mean_without, 2) + '</td>';
            html += '<td class="score-positive">' + (card.score >= 0 ? '+' : '') + fmt(card.score, 2) + '</td></tr>';
        });
        html += '</tbody></table></div></div>';

        // Low performers
        html += '<div><h3>Low Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr><th>#</th><th>Card</th><th>Cost</th><th>Effects</th>';
        html += '<th>Avg With</th><th>Avg Without</th><th>Impact</th></tr></thead><tbody>';
        cp.low_performing.forEach((card, i) => {
            html += '<tr><td>' + (i + 1) + '</td>';
            html += '<td style="text-align:left">' + cardLink(card.name) + '</td>';
            html += '<td>' + escapeHtml(card.cost) + '</td>';
            html += '<td style="text-align:left">' + escapeHtml(card.effects) + '</td>';
            html += '<td>' + fmt(card.mean_with, 2) + '</td>';
            html += '<td>' + fmt(card.mean_without, 2) + '</td>';
            html += '<td class="score-negative">' + (card.score >= 0 ? '+' : '') + fmt(card.score, 2) + '</td></tr>';
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
                html += escapeHtml(r.recommendation);
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
                html += escapeHtml(r.recommendation);
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
                + ' &mdash; model explains ' + fmt(reg.r_squared * 100, 1)
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

    // -- Public API --

    /**
     * Render simulation results into a container element.
     *
     * @param {HTMLElement} container - Target element to render into
     * @param {Array} results - Array of result dicts (from result_to_dict)
     * @param {string} deckName - Deck name for the title
     */
    function render(container, results, deckName) {
        const isOptimization = results.length > 0 && results[0].opt_config !== undefined;

        let html = '<div class="results-content">';
        html += '<h1>Results: ' + escapeHtml(deckName) + '</h1>';

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
        if (!isOptimization) {
            renderCharts(results);
        }
        initReplayViewer(results);
        rebindTooltips();
    }

    return {render, rebindTooltips, renderCharts, initReplayViewer};
})();

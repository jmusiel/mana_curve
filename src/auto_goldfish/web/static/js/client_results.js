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
                <dt>Mana V+D</dt>
                <dd>Total mana spent on value (no-effect) and draw spells. Ramp excluded because it pays for itself. Higher = more resources deployed.</dd>
                <dt>Value / Draw / Ramp</dt>
                <dd>Mana breakdown by card type. Draw > ramp priority (cards with both count as draw).</dd>
                <dt>Total</dt>
                <dd>Total mana spent on all spells (value + draw + ramp).</dd>
                <dt>Hand Sum</dt>
                <dd>Sum of min(hand_size, 7) per turn. Measures card availability across the game.</dd>
                <dt>Consistency</dt>
                <dd>How reliably the deck avoids low-mana games (0&ndash;1.2 scale). 1.0 = perfectly consistent. Computed from cumulative mana distribution.</dd>
                <dt>Bad Turns</dt>
                <dd>Average turns where no spells were cast and the deck wasn&rsquo;t empty. Lower = better.</dd>
                <dt>Mid Turns</dt>
                <dd>Average turns with fewer than 2 spells and mana spent below the turn number. Lower = better.</dd>
                <dt>Avg Lands / Avg Mulls</dt>
                <dd>Average lands played and mulligans taken per game.</dd>
                <dt>Avg Draws / Avg Spells</dt>
                <dd>Average cards drawn and spells cast per game.</dd>
                <dt>25th / 50th / 75th</dt>
                <dd>Percentiles of value+draw mana spent showing distribution spread.</dd>
            </dl>
        </details>`;
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
        if (isOptimization) html += '<th>Rank</th><th>Configuration</th>';
        html += '<th>Lands</th><th>Mana V+D</th><th>Value</th><th>Draw</th><th>Ramp</th>';
        html += '<th>Total</th><th>Hand Sum</th><th>Consistency</th><th>Bad Turns</th>';
        html += '<th>Mid Turns</th><th>Avg Lands</th><th>Avg Mulls</th>';
        html += '<th>Avg Draws</th><th>Avg Spells</th>';
        html += '<th>25th</th><th>50th</th><th>75th</th></tr></thead><tbody>';

        for (let i = 0; i < results.length; i++) {
            const r = results[i];
            const manaMargin = r.ci_mean_mana ? (r.ci_mean_mana[1] - r.ci_mean_mana[0]) / 2 : 0;
            const conMargin = r.ci_consistency ? (r.ci_consistency[1] - r.ci_consistency[0]) / 2 : 0;
            html += '<tr' + (isOptimization && i === 0 ? ' style="font-weight:bold; background:#e8f5e9;"' : '') + '>';
            if (isOptimization) {
                html += '<td>' + (i + 1) + '</td>';
                html += '<td style="text-align:left">' + formatConfig(r.opt_config || 'Base deck') + '</td>';
            }
            html += '<td>' + r.land_count + '</td>';
            html += '<td>' + fmt(r.mean_mana, 2) + ' <small>&plusmn;' + fmt(manaMargin, 2) + '</small></td>';
            html += '<td>' + fmt(r.mean_mana_value ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mana_draw ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mana_ramp ?? 0, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mana_total ?? 0, 2) + '</td>';
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
        html += '<p class="card-perf-summary">Based on ' + cp.total_top_games
            + ' top-quartile and ' + cp.total_low_games + ' low-quartile games.</p>';
        html += '<div class="card-perf-grid">';

        // High performers
        html += '<div><h3>Top Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr><th>#</th><th>Card</th><th>Cost</th><th>Effects</th>';
        html += '<th>Top Rate</th><th>Low Rate</th><th>Score</th></tr></thead><tbody>';
        cp.high_performing.forEach((card, i) => {
            html += '<tr><td>' + (i + 1) + '</td>';
            html += '<td style="text-align:left">' + cardLink(card.name) + '</td>';
            html += '<td>' + escapeHtml(card.cost) + '</td>';
            html += '<td style="text-align:left">' + escapeHtml(card.effects) + '</td>';
            html += '<td>' + fmt(card.top_rate * 100, 1) + '%</td>';
            html += '<td>' + fmt(card.low_rate * 100, 1) + '%</td>';
            html += '<td class="score-positive">' + (card.score >= 0 ? '+' : '') + fmt(card.score, 2) + '</td></tr>';
        });
        html += '</tbody></table></div></div>';

        // Low performers
        html += '<div><h3>Low Performers</h3><div class="table-wrap"><table class="stats-table">';
        html += '<thead><tr><th>#</th><th>Card</th><th>Cost</th><th>Effects</th>';
        html += '<th>Top Rate</th><th>Low Rate</th><th>Score</th></tr></thead><tbody>';
        cp.low_performing.forEach((card, i) => {
            html += '<tr><td>' + (i + 1) + '</td>';
            html += '<td style="text-align:left">' + cardLink(card.name) + '</td>';
            html += '<td>' + escapeHtml(card.cost) + '</td>';
            html += '<td style="text-align:left">' + escapeHtml(card.effects) + '</td>';
            html += '<td>' + fmt(card.top_rate * 100, 1) + '%</td>';
            html += '<td>' + fmt(card.low_rate * 100, 1) + '%</td>';
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

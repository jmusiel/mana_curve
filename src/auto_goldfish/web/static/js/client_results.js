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

    // -- Section renderers --

    function renderSummaryTable(results) {
        let html = '<h2>Summary Statistics</h2>';
        html += `<details class="metric-descriptions">
            <summary>Metric Definitions</summary>
            <dl class="metric-list">
                <dt>Mana (EV)</dt>
                <dd>Total mana spent on non-ramp spells over all turns. Ramp cards excluded because they pay for themselves. Higher = more resources deployed.</dd>
                <dt>Consistency</dt>
                <dd>How reliably the deck avoids low-mana games (0&ndash;1.2 scale). 1.0 = perfectly consistent. Computed from cumulative mana distribution.</dd>
                <dt>Bad Turns</dt>
                <dd>Average turns where no spells were cast and the deck wasn&rsquo;t empty. Lower = better.</dd>
                <dt>Mid Turns</dt>
                <dd>Average turns with fewer than 2 spells and mana spent below the turn number. Lower = better.</dd>
                <dt>Avg Lands / Avg Mulls</dt>
                <dd>Average lands played and mulligans taken per game.</dd>
                <dt>25th / 50th / 75th</dt>
                <dd>Percentiles of total mana spent showing distribution spread.</dd>
            </dl>
        </details>`;
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
        html += '<th>Lands</th><th>Mana (EV)</th><th>Consistency</th><th>Bad Turns</th>';
        html += '<th>Mid Turns</th><th>Avg Lands</th><th>Avg Mulls</th>';
        html += '<th>25th</th><th>50th</th><th>75th</th></tr></thead><tbody>';

        for (const r of results) {
            const manaMargin = r.ci_mean_mana ? (r.ci_mean_mana[1] - r.ci_mean_mana[0]) / 2 : 0;
            const conMargin = r.ci_consistency ? (r.ci_consistency[1] - r.ci_consistency[0]) / 2 : 0;
            html += '<tr>';
            html += '<td>' + r.land_count + '</td>';
            html += '<td>' + fmt(r.mean_mana, 2) + ' <small>&plusmn;' + fmt(manaMargin, 2) + '</small></td>';
            html += '<td>' + fmt(r.consistency, 3) + ' <small>&plusmn;' + fmt(conMargin, 4) + '</small></td>';
            html += '<td>' + fmt(r.mean_bad_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mid_turns, 2) + '</td>';
            html += '<td>' + fmt(r.mean_lands, 2) + '</td>';
            html += '<td>' + fmt(r.mean_mulls, 2) + '</td>';
            html += '<td>' + fmt(r.percentile_25, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_50, 1) + '</td>';
            html += '<td>' + fmt(r.percentile_75, 1) + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        return html;
    }

    function renderDistributionTable(results) {
        if (!results[0].distribution_stats) return '';

        let html = '<h2>Distribution Statistics</h2>';
        html += `<details class="metric-descriptions">
            <summary>Distribution Definitions</summary>
            <dl class="metric-list">
                <dt>Distribution Stats</dt>
                <dd>Fraction of games in calibrated performance buckets. Thresholds set from first 10% of simulations. Values above the nominal percentage indicate overperformance.</dd>
            </dl>
        </details>`;
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr>';
        html += '<th>Lands</th><th>Top 1%</th><th>Top 10%</th><th>Top 25%</th><th>Top 50%</th>';
        html += '<th>Low 50%</th><th>Low 25%</th><th>Low 10%</th><th>Low 1%</th>';
        html += '</tr></thead><tbody>';

        const keys = ['top_centile', 'top_decile', 'top_quartile', 'top_half',
                      'low_half', 'low_quartile', 'low_decile', 'low_centile'];

        for (const r of results) {
            html += '<tr><td>' + r.land_count + '</td>';
            for (const k of keys) {
                html += '<td>' + fmt((r.distribution_stats[k] || 0) * 100, 1) + '%</td>';
            }
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
            <div class="chart-container"><canvas id="distributionChart"></canvas></div>
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
        ['manaChart', 'distributionChart', 'consistencyChart'].forEach(id => {
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

        // Distribution stats
        if (data[0].distribution_stats) {
            const distKeys = ['top_centile', 'top_decile', 'top_quartile', 'top_half',
                              'low_half', 'low_quartile', 'low_decile', 'low_centile'];
            const distLabels = ['Top 1%', 'Top 10%', 'Top 25%', 'Top 50%',
                                'Low 50%', 'Low 25%', 'Low 10%', 'Low 1%'];
            const colors = ['#16a34a', '#22c55e', '#4ade80', '#86efac',
                            '#fca5a5', '#f87171', '#ef4444', '#dc2626'];

            new Chart(document.getElementById('distributionChart'), {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: distKeys.map((key, i) => ({
                        label: distLabels[i],
                        data: data.map(d => (d.distribution_stats[key] || 0) * 100),
                        backgroundColor: colors[i],
                    }))
                },
                options: {
                    responsive: true,
                    plugins: {title: {display: true, text: 'Distribution Stats (%)'}},
                    scales: {
                        x: {title: {display: true, text: 'Land Count'}},
                        y: {title: {display: true, text: 'Percentage'}}
                    }
                }
            });
        }

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
        let html = '<div class="results-content">';
        html += '<h1>Results: ' + escapeHtml(deckName) + '</h1>';
        html += renderSummaryTable(results);
        html += renderDistributionTable(results);
        html += renderCardPerformance(results);
        html += renderChartCanvases();
        html += renderReplayHTML(results);
        html += '</div>';

        container.innerHTML = html;

        // Render interactive components after DOM is updated
        renderCharts(results);
        initReplayViewer(results);
        rebindTooltips();
    }

    return {render, rebindTooltips, renderCharts, initReplayViewer};
})();

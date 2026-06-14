/**
 * CASTER share-card helpers — pure, DOM-free data prep so it can be unit-tested.
 *
 * The canvas drawing + clipboard/Web-Share glue lives in client_results.js
 * (it needs a real DOM and can't be tested headlessly). This module holds only
 * the bug-prone logic: deriving the overall headline and assembling the
 * per-stat list a score card renders.
 *
 * Browser: loaded via <script> before client_results.js; exposes
 *          window.CasterCard.
 * Node:    require('./caster_card.js') returns the same object.
 */
(function (root) {
    'use strict';

    /**
     * The overall headline number: prefer the engine-computed score.overall
     * (plain mean of the six axes); fall back to computing the mean from the
     * provided stat keys so older cached results still produce a headline.
     */
    function overallOf(score, stats) {
        if (score && typeof score.overall === 'number') return score.overall;
        var vals = (stats || []).map(function (s) {
            return (score && typeof score[s.key] === 'number') ? score[s.key] : 0;
        });
        if (!vals.length) return 0;
        var sum = vals.reduce(function (a, b) { return a + b; }, 0);
        return Math.round((sum / vals.length) * 10) / 10;
    }

    /**
     * Build everything a CASTER score card needs from a deck_score object.
     * `stats` is the CASTER_STATS list: [{name, key, color}, ...].
     * Returns {deckName, overall, stats: [{name, value, color}, ...]}.
     */
    function cardData(score, deckName, stats) {
        score = score || {};
        stats = stats || [];
        var statList = stats.map(function (s) {
            return {
                name: s.name,
                value: (typeof score[s.key] === 'number') ? score[s.key] : 0,
                color: s.color
            };
        });
        return {
            deckName: deckName || 'deck',
            overall: overallOf(score, stats),
            stats: statList
        };
    }

    var CasterCard = {overallOf: overallOf, cardData: cardData};

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = CasterCard;
    } else {
        root.CasterCard = CasterCard;
    }
})(typeof window !== 'undefined' ? window : this);

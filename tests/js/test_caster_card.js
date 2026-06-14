/**
 * Unit tests for the CASTER share-card pure data prep.
 *
 * Run with:  node tests/js/test_caster_card.js
 *
 * Uses Node's built-in assert module (no dependencies required). Covers only
 * the DOM-free logic in caster_card.js; the canvas/clipboard/share glue in
 * client_results.js is verified by running the app.
 */
'use strict';

var assert = require('assert');
var CC = require('../../src/auto_goldfish/web/static/js/caster_card.js');

var passed = 0;
var failed = 0;
var failures = [];

function test(name, fn) {
    try {
        fn();
        passed++;
    } catch (e) {
        failed++;
        failures.push({name: name, error: e});
        console.error('  FAIL: ' + name);
        console.error('    ' + e.message);
    }
}

// Representative CASTER_STATS shape (name/key/color) as passed from client_results.js.
var STATS = [
    {name: 'Consistency', key: 'consistency', color: '#eab308'},
    {name: 'Acceleration', key: 'acceleration', color: '#ef4444'},
    {name: 'Snowball', key: 'snowball', color: '#8b5cf6'},
    {name: 'Tuning', key: 'tuning', color: '#22c55e'},
    {name: 'Efficiency', key: 'efficiency', color: '#3b82f6'},
    {name: 'Reach', key: 'reach', color: '#f97316'},
];

var FULL_SCORE = {
    consistency: 6, acceleration: 4, snowball: 8,
    tuning: 5, efficiency: 7, reach: 6, overall: 6.0,
};

console.log('--- overallOf tests ---');

test('overallOf prefers engine-provided score.overall', function () {
    assert.strictEqual(CC.overallOf({overall: 7.3}, STATS), 7.3);
});

test('overallOf falls back to plain mean when overall is absent', function () {
    var score = {consistency: 6, acceleration: 4, snowball: 8, tuning: 5, efficiency: 7, reach: 6};
    assert.strictEqual(CC.overallOf(score, STATS), Math.round((6 + 4 + 8 + 5 + 7 + 6) / 6 * 10) / 10);
});

test('overallOf treats missing axis values as 0 in the fallback', function () {
    // Only two axes present -> mean over all six keys (missing = 0).
    var score = {consistency: 6, reach: 6};
    assert.strictEqual(CC.overallOf(score, STATS), Math.round((6 + 0 + 0 + 0 + 0 + 6) / 6 * 10) / 10);
});

test('overallOf returns 0 with no stats', function () {
    assert.strictEqual(CC.overallOf({}, []), 0);
});

console.log('--- cardData tests ---');

test('cardData returns the six stats with name/value/color', function () {
    var d = CC.cardData(FULL_SCORE, 'My Deck', STATS);
    assert.strictEqual(d.stats.length, 6);
    assert.deepStrictEqual(d.stats[0], {name: 'Consistency', value: 6, color: '#eab308'});
    assert.deepStrictEqual(d.stats[5], {name: 'Reach', value: 6, color: '#f97316'});
});

test('cardData carries the overall headline', function () {
    assert.strictEqual(CC.cardData(FULL_SCORE, 'My Deck', STATS).overall, 6.0);
});

test('cardData defaults a blank deck name to "deck"', function () {
    assert.strictEqual(CC.cardData(FULL_SCORE, '', STATS).deckName, 'deck');
    assert.strictEqual(CC.cardData(FULL_SCORE, undefined, STATS).deckName, 'deck');
});

test('cardData preserves the given deck name', function () {
    assert.strictEqual(CC.cardData(FULL_SCORE, 'Vren', STATS).deckName, 'Vren');
});

test('cardData defaults missing axis values to 0', function () {
    var d = CC.cardData({consistency: 9}, 'd', STATS);
    assert.strictEqual(d.stats[0].value, 9);
    assert.strictEqual(d.stats[1].value, 0);
});

test('cardData is safe with empty/missing args', function () {
    var d = CC.cardData(undefined, undefined, undefined);
    assert.strictEqual(d.deckName, 'deck');
    assert.strictEqual(d.overall, 0);
    assert.deepStrictEqual(d.stats, []);
});

console.log('\n=== Results: ' + passed + ' passed, ' + failed + ' failed ===');
if (failed > 0) {
    process.exit(1);
}

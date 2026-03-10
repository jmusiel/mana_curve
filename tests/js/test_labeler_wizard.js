/**
 * Unit tests for the labeler wizard pure logic module.
 *
 * Run with:  node tests/js/test_labeler_wizard.js
 *
 * Uses Node's built-in assert module (no dependencies required).
 */
'use strict';

var assert = require('assert');
var LW = require('../../src/auto_goldfish/web/static/js/labeler_wizard.js');

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

// ── Helper ──────────────────────────────────────────────────────

function freshCtx() {
    return {state: {}, amountContext: ''};
}

function runTree(steps) {
    // steps: [{step, value}, ...]  — walk through the tree
    var ctx = freshCtx();
    var nextStep = LW.getFirstStep();
    var log = [];
    for (var i = 0; i < steps.length; i++) {
        assert.strictEqual(nextStep, steps[i].step, 'Expected step ' + steps[i].step + ' but got ' + nextStep + ' at index ' + i);
        nextStep = LW.applyDecision(steps[i].step, steps[i].value, ctx);
        log.push({stepId: steps[i].step, chosenValue: steps[i].value});
    }
    return {ctx: ctx, nextStep: nextStep, log: log};
}

// ═══════════════════════════════════════════════════════════════
// applyDecision — state machine routing
// ═══════════════════════════════════════════════════════════════

console.log('--- applyDecision tests ---');

test('cost -> classify', function () {
    var ctx = freshCtx();
    var next = LW.applyDecision('cost', 3, ctx);
    assert.strictEqual(next, 'classify');
    assert.strictEqual(ctx.state.costOverride, 3);
});

test('classify=draw -> draw-type', function () {
    var ctx = freshCtx();
    var next = LW.applyDecision('classify', 'draw', ctx);
    assert.strictEqual(next, 'draw-type');
    assert.strictEqual(ctx.state.mainType, 'draw');
});

test('classify=ramp -> ramp', function () {
    var ctx = freshCtx();
    var next = LW.applyDecision('classify', 'ramp', ctx);
    assert.strictEqual(next, 'ramp');
    assert.strictEqual(ctx.state.mainType, 'ramp');
});

test('classify=both -> ramp', function () {
    var ctx = freshCtx();
    var next = LW.applyDecision('classify', 'both', ctx);
    assert.strictEqual(next, 'ramp');
    assert.strictEqual(ctx.state.mainType, 'both');
});

test('classify=neither -> _done', function () {
    var ctx = freshCtx();
    var next = LW.applyDecision('classify', 'neither', ctx);
    assert.strictEqual(next, '_done');
    assert.strictEqual(ctx.state.mainType, 'neither');
});

test('ramp=mana_rock -> amount', function () {
    var ctx = freshCtx();
    ctx.state.mainType = 'ramp';
    var next = LW.applyDecision('ramp', 'mana_rock', ctx);
    assert.strictEqual(next, 'amount');
    assert.strictEqual(ctx.amountContext, 'ramp');
});

test('ramp=cost_reducer -> spell-type', function () {
    var ctx = freshCtx();
    ctx.state.mainType = 'ramp';
    var next = LW.applyDecision('ramp', 'cost_reducer', ctx);
    assert.strictEqual(next, 'spell-type');
});

test('full mana rock path: cost -> classify=ramp -> ramp=mana_rock -> amount -> tempo -> _done', function () {
    var result = runTree([
        {step: 'cost', value: 2},
        {step: 'classify', value: 'ramp'},
        {step: 'ramp', value: 'mana_rock'},
        {step: 'amount', value: 1},
        {step: 'tempo', value: 'untapped'},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.rampType, 'mana_rock');
    assert.strictEqual(result.ctx.state.tempo, 'untapped');
});

test('full mana dork path: amount -> _done (auto summoning_sick)', function () {
    var result = runTree([
        {step: 'cost', value: 1},
        {step: 'classify', value: 'ramp'},
        {step: 'ramp', value: 'mana_dork'},
        {step: 'amount', value: 1},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.tempo, 'summoning_sick');
});

test('full ritual path: amount -> _done', function () {
    var result = runTree([
        {step: 'cost', value: 1},
        {step: 'classify', value: 'ramp'},
        {step: 'ramp', value: 'ritual'},
        {step: 'amount', value: 3},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.rampAmount, 3);
});

test('full cost reducer path: spell-type -> amount -> _done', function () {
    var result = runTree([
        {step: 'cost', value: 3},
        {step: 'classify', value: 'ramp'},
        {step: 'ramp', value: 'cost_reducer'},
        {step: 'spell-type', value: 'creature'},
        {step: 'amount', value: 1},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.spellType, 'creature');
});

test('full land ramp path: amount -> tempo -> _done', function () {
    var result = runTree([
        {step: 'cost', value: 4},
        {step: 'classify', value: 'ramp'},
        {step: 'ramp', value: 'land_ramp'},
        {step: 'amount', value: 1},
        {step: 'tempo', value: 'tapped'},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.rampType, 'land_ramp');
});

test('full draw immediate path', function () {
    var result = runTree([
        {step: 'cost', value: 4},
        {step: 'classify', value: 'draw'},
        {step: 'draw-type', value: 'draw_only'},
        {step: 'draw-timing', value: 'immediate'},
        {step: 'amount', value: 3},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.drawAmount, 3);
});

test('full draw per_cast path includes trigger', function () {
    var result = runTree([
        {step: 'cost', value: 3},
        {step: 'classify', value: 'draw'},
        {step: 'draw-type', value: 'draw_only'},
        {step: 'draw-timing', value: 'per_cast'},
        {step: 'trigger', value: 'creature'},
        {step: 'amount', value: 1},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.trigger, 'creature');
});

test('draw_discard path has two amount steps', function () {
    var result = runTree([
        {step: 'cost', value: 2},
        {step: 'classify', value: 'draw'},
        {step: 'draw-type', value: 'draw_discard'},
        {step: 'draw-timing', value: 'immediate'},
        {step: 'amount', value: 2},    // draw amount
        {step: 'amount', value: 1},    // discard amount
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.drawAmount, 2);
    assert.strictEqual(result.ctx.state.discardAmount, 1);
});

test('both path: ramp then draw', function () {
    var result = runTree([
        {step: 'cost', value: 3},
        {step: 'classify', value: 'both'},
        {step: 'ramp', value: 'mana_rock'},
        {step: 'amount', value: 1},
        {step: 'tempo', value: 'untapped'},
        {step: 'draw-type', value: 'draw_only'},
        {step: 'draw-timing', value: 'per_turn'},
        {step: 'amount', value: 1},
    ]);
    assert.strictEqual(result.nextStep, '_done');
    assert.strictEqual(result.ctx.state.mainType, 'both');
    assert.strictEqual(result.ctx.state.rampType, 'mana_rock');
    assert.strictEqual(result.ctx.state.drawTiming, 'per_turn');
});

// ═══════════════════════════════════════════════════════════════
// buildCategories
// ═══════════════════════════════════════════════════════════════

console.log('--- buildCategories tests ---');

test('neither produces empty categories', function () {
    var cats = LW.buildCategories({mainType: 'neither'});
    assert.deepStrictEqual(cats, []);
});

test('mana rock produces correct category', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'mana_rock', rampAmount: 2, tempo: 'untapped'});
    assert.strictEqual(cats.length, 1);
    assert.strictEqual(cats[0].category, 'ramp');
    assert.strictEqual(cats[0].producer.mana_amount, 2);
    assert.strictEqual(cats[0].producer.tempo, 'untapped');
    assert.strictEqual(cats[0].immediate, false);
});

test('mana rock tapped sets tempo correctly', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'mana_rock', rampAmount: 1, tempo: 'tapped'});
    assert.strictEqual(cats[0].producer.tempo, 'tapped');
});

test('mana dork sets summoning_sick tempo', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'mana_dork', rampAmount: 1, tempo: 'summoning_sick'});
    assert.strictEqual(cats[0].producer.tempo, 'summoning_sick');
});

test('ritual produces immediate=true', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'ritual', rampAmount: 3});
    assert.strictEqual(cats[0].immediate, true);
    assert.strictEqual(cats[0].producer.mana_amount, 3);
});

test('land ramp produces land_to_battlefield', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'land_ramp', rampAmount: 1, tempo: 'tapped'});
    assert.strictEqual(cats[0].land_to_battlefield.count, 1);
    assert.strictEqual(cats[0].land_to_battlefield.tempo, 'tapped');
});

test('cost reducer produces reducer', function () {
    var cats = LW.buildCategories({mainType: 'ramp', rampType: 'cost_reducer', spellType: 'creature', rampAmount: 1});
    assert.strictEqual(cats[0].reducer.spell_type, 'creature');
    assert.strictEqual(cats[0].reducer.amount, 1);
});

test('immediate draw', function () {
    var cats = LW.buildCategories({mainType: 'draw', drawType: 'draw_only', drawTiming: 'immediate', drawAmount: 3});
    assert.strictEqual(cats.length, 1);
    assert.strictEqual(cats[0].category, 'draw');
    assert.strictEqual(cats[0].immediate, true);
    assert.strictEqual(cats[0].amount, 3);
});

test('per_turn draw', function () {
    var cats = LW.buildCategories({mainType: 'draw', drawType: 'draw_only', drawTiming: 'per_turn', drawAmount: 1});
    assert.strictEqual(cats[0].per_turn.amount, 1);
    assert.strictEqual(cats[0].immediate, false);
});

test('per_cast draw', function () {
    var cats = LW.buildCategories({mainType: 'draw', drawType: 'draw_only', drawTiming: 'per_cast', drawAmount: 1, trigger: 'creature'});
    assert.strictEqual(cats[0].per_cast.amount, 1);
    assert.strictEqual(cats[0].per_cast.trigger, 'creature');
});

test('draw_discard produces draw + discard categories', function () {
    var cats = LW.buildCategories({mainType: 'draw', drawType: 'draw_discard', drawTiming: 'immediate', drawAmount: 2, discardAmount: 1});
    assert.strictEqual(cats.length, 2);
    assert.strictEqual(cats[0].category, 'draw');
    assert.strictEqual(cats[1].category, 'discard');
    assert.strictEqual(cats[1].amount, 1);
});

test('both produces ramp + draw categories', function () {
    var cats = LW.buildCategories({mainType: 'both', rampType: 'mana_rock', rampAmount: 1, tempo: 'untapped', drawType: 'draw_only', drawTiming: 'per_turn', drawAmount: 1});
    assert.strictEqual(cats.length, 2);
    assert.strictEqual(cats[0].category, 'ramp');
    assert.strictEqual(cats[1].category, 'draw');
});

// ═══════════════════════════════════════════════════════════════
// validateCategories
// ═══════════════════════════════════════════════════════════════

console.log('--- validateCategories tests ---');

test('valid ramp passes validation', function () {
    var errors = LW.validateCategories([{category: 'ramp', immediate: false, producer: {mana_amount: 1, tempo: 'untapped'}}]);
    assert.deepStrictEqual(errors, []);
});

test('ramp missing variant fails validation', function () {
    var errors = LW.validateCategories([{category: 'ramp', immediate: false}]);
    assert.ok(errors.length > 0);
});

test('immediate draw missing amount fails', function () {
    var errors = LW.validateCategories([{category: 'draw', immediate: true}]);
    assert.ok(errors.length > 0);
});

test('discard missing amount fails', function () {
    var errors = LW.validateCategories([{category: 'discard'}]);
    assert.ok(errors.length > 0);
});

test('invalid category fails', function () {
    var errors = LW.validateCategories([{category: 'bogus'}]);
    assert.ok(errors.length > 0);
});

test('valid draw per_turn passes', function () {
    var errors = LW.validateCategories([{category: 'draw', immediate: false, per_turn: {amount: 1}}]);
    assert.deepStrictEqual(errors, []);
});

// ═══════════════════════════════════════════════════════════════
// decodeAnnotation
// ═══════════════════════════════════════════════════════════════

console.log('--- decodeAnnotation tests ---');

test('null annotation returns empty log', function () {
    var log = LW.decodeAnnotation(null, {cmc: 2});
    assert.deepStrictEqual(log, []);
});

test('empty categories decodes as neither', function () {
    var log = LW.decodeAnnotation({categories: []}, {cmc: 3});
    assert.strictEqual(log.length, 2); // cost + classify=neither
    assert.strictEqual(log[0].stepId, 'cost');
    assert.strictEqual(log[0].chosenValue, 3);
    assert.strictEqual(log[1].stepId, 'classify');
    assert.strictEqual(log[1].chosenValue, 'neither');
});

test('override_cmc used when present', function () {
    var log = LW.decodeAnnotation({categories: [], override_cmc: 0}, {cmc: 5});
    assert.strictEqual(log[0].chosenValue, 0);
});

test('mana rock annotation round-trips', function () {
    var annotation = {categories: [{category: 'ramp', immediate: false, producer: {mana_amount: 2, tempo: 'untapped'}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 2});

    // cost, classify=ramp, ramp=mana_rock, amount=2, tempo=untapped
    assert.strictEqual(log.length, 5);
    assert.strictEqual(log[1].chosenValue, 'ramp');
    assert.strictEqual(log[2].chosenValue, 'mana_rock');
    assert.strictEqual(log[3].chosenValue, 2);
    assert.strictEqual(log[4].chosenValue, 'untapped');
});

test('mana dork annotation decoded', function () {
    var annotation = {categories: [{category: 'ramp', immediate: false, producer: {mana_amount: 1, tempo: 'summoning_sick'}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 1});
    assert.strictEqual(log[2].chosenValue, 'mana_dork');
});

test('ritual annotation decoded', function () {
    var annotation = {categories: [{category: 'ramp', immediate: true, producer: {mana_amount: 3}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 1});
    assert.strictEqual(log[2].chosenValue, 'ritual');
});

test('cost reducer annotation decoded', function () {
    var annotation = {categories: [{category: 'ramp', immediate: false, reducer: {spell_type: 'creature', amount: 1}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 3});
    assert.strictEqual(log[2].chosenValue, 'cost_reducer');
    assert.strictEqual(log[3].chosenValue, 'creature'); // spell-type
    assert.strictEqual(log[4].chosenValue, 1); // amount
});

test('land ramp annotation decoded', function () {
    var annotation = {categories: [{category: 'ramp', immediate: true, land_to_battlefield: {count: 1, tempo: 'tapped'}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 4});
    assert.strictEqual(log[2].chosenValue, 'land_ramp');
    assert.strictEqual(log[3].chosenValue, 1); // amount (count)
    assert.strictEqual(log[4].chosenValue, 'tapped'); // tempo
});

test('immediate draw decoded', function () {
    var annotation = {categories: [{category: 'draw', immediate: true, amount: 3}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 4});
    assert.strictEqual(log[1].chosenValue, 'draw');
    assert.strictEqual(log[2].chosenValue, 'draw_only');
    assert.strictEqual(log[3].chosenValue, 'immediate');
    assert.strictEqual(log[4].chosenValue, 3);
});

test('per_cast draw with trigger decoded', function () {
    var annotation = {categories: [{category: 'draw', immediate: false, per_cast: {amount: 1, trigger: 'creature'}}]};
    var log = LW.decodeAnnotation(annotation, {cmc: 3});
    assert.strictEqual(log[3].chosenValue, 'per_cast');
    assert.strictEqual(log[4].chosenValue, 'creature'); // trigger
    assert.strictEqual(log[5].chosenValue, 1); // amount
});

test('draw_discard decoded with discard amount', function () {
    var annotation = {
        categories: [
            {category: 'draw', immediate: true, amount: 2},
            {category: 'discard', amount: 1},
        ]
    };
    var log = LW.decodeAnnotation(annotation, {cmc: 2});
    assert.strictEqual(log[2].chosenValue, 'draw_discard');
    // Last entry should be discard amount
    var lastAmount = log[log.length - 1];
    assert.strictEqual(lastAmount.chosenValue, 1);
    assert.ok(lastAmount.prompt.toLowerCase().indexOf('discard') >= 0);
});

test('both annotation decoded (ramp + draw)', function () {
    var annotation = {
        categories: [
            {category: 'ramp', immediate: false, producer: {mana_amount: 1, tempo: 'untapped'}},
            {category: 'draw', immediate: false, per_turn: {amount: 1}},
        ]
    };
    var log = LW.decodeAnnotation(annotation, {cmc: 3});
    assert.strictEqual(log[1].chosenValue, 'both');
    // Should have ramp steps then draw steps
    var stepIds = log.map(function (e) { return e.stepId; });
    assert.ok(stepIds.indexOf('ramp') >= 0);
    assert.ok(stepIds.indexOf('draw-type') >= 0);
});

// ═══════════════════════════════════════════════════════════════
// Round-trip: decode -> replay -> build should match original
// ═══════════════════════════════════════════════════════════════

console.log('--- round-trip tests ---');

function roundTrip(annotation, card) {
    var log = LW.decodeAnnotation(annotation, card);
    var result = LW.replayDecisions(log);
    var cats = LW.buildCategories(result.state);
    return cats;
}

test('round-trip mana rock', function () {
    var orig = {categories: [{category: 'ramp', immediate: false, producer: {mana_amount: 2, tempo: 'untapped'}}]};
    var cats = roundTrip(orig, {cmc: 2});
    assert.strictEqual(cats.length, 1);
    assert.strictEqual(cats[0].producer.mana_amount, 2);
    assert.strictEqual(cats[0].producer.tempo, 'untapped');
});

test('round-trip ritual', function () {
    var orig = {categories: [{category: 'ramp', immediate: true, producer: {mana_amount: 3}}]};
    var cats = roundTrip(orig, {cmc: 1});
    assert.strictEqual(cats[0].immediate, true);
    assert.strictEqual(cats[0].producer.mana_amount, 3);
});

test('round-trip immediate draw', function () {
    var orig = {categories: [{category: 'draw', immediate: true, amount: 3}]};
    var cats = roundTrip(orig, {cmc: 4});
    assert.strictEqual(cats[0].amount, 3);
    assert.strictEqual(cats[0].immediate, true);
});

test('round-trip draw/discard', function () {
    var orig = {categories: [{category: 'draw', immediate: true, amount: 2}, {category: 'discard', amount: 1}]};
    var cats = roundTrip(orig, {cmc: 2});
    assert.strictEqual(cats.length, 2);
    assert.strictEqual(cats[0].category, 'draw');
    assert.strictEqual(cats[1].category, 'discard');
    assert.strictEqual(cats[1].amount, 1);
});

test('round-trip both (ramp + draw)', function () {
    var orig = {
        categories: [
            {category: 'ramp', immediate: false, producer: {mana_amount: 1, tempo: 'untapped'}},
            {category: 'draw', immediate: false, per_turn: {amount: 1}},
        ]
    };
    var cats = roundTrip(orig, {cmc: 3});
    assert.strictEqual(cats.length, 2);
    assert.strictEqual(cats[0].category, 'ramp');
    assert.strictEqual(cats[1].category, 'draw');
});

// ═══════════════════════════════════════════════════════════════
// replayDecisions
// ═══════════════════════════════════════════════════════════════

console.log('--- replayDecisions tests ---');

test('replay empty decisions returns first step', function () {
    var result = LW.replayDecisions([]);
    assert.strictEqual(result.nextStep, 'cost');
    assert.deepStrictEqual(result.state, {});
});

test('replay partial decisions resumes at correct step', function () {
    var result = LW.replayDecisions([
        {stepId: 'cost', chosenValue: 2},
        {stepId: 'classify', chosenValue: 'ramp'},
    ]);
    assert.strictEqual(result.nextStep, 'ramp');
    assert.strictEqual(result.state.mainType, 'ramp');
});

// ═══════════════════════════════════════════════════════════════
// describePriorAnnotation
// ═══════════════════════════════════════════════════════════════

console.log('--- describePriorAnnotation tests ---');

test('null annotation', function () {
    assert.strictEqual(LW.describePriorAnnotation(null), 'No effects');
});

test('empty categories', function () {
    assert.strictEqual(LW.describePriorAnnotation({categories: []}), 'No effects');
});

test('mana rock description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'ramp', immediate: false, producer: {mana_amount: 2}}]});
    assert.ok(desc.indexOf('produces 2 mana') >= 0);
});

test('immediate draw description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'draw', immediate: true, amount: 3}]});
    assert.ok(desc.indexOf('Draw 3') >= 0);
});

test('per_cast draw description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'draw', immediate: false, per_cast: {amount: 1, trigger: 'creature'}}]});
    assert.ok(desc.indexOf('per creature cast') >= 0);
});

test('discard description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'discard', amount: 2}]});
    assert.ok(desc.indexOf('Discard 2') >= 0);
});

test('land ramp description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'ramp', land_to_battlefield: {count: 1, tempo: 'tapped'}}]});
    assert.ok(desc.indexOf('fetch 1 land') >= 0);
});

test('cost reducer description', function () {
    var desc = LW.describePriorAnnotation({categories: [{category: 'ramp', reducer: {spell_type: 'creature', amount: 1}}]});
    assert.ok(desc.indexOf('reduce creature cost') >= 0);
});

// ═══════════════════════════════════════════════════════════════
// getOptionsForStep
// ═══════════════════════════════════════════════════════════════

console.log('--- getOptionsForStep tests ---');

test('classify options returned', function () {
    var opts = LW.getOptionsForStep('classify', 'draw');
    assert.strictEqual(opts.length, 4);
});

test('amount shows 1,2,3 for small values', function () {
    var opts = LW.getOptionsForStep('amount', 2);
    assert.strictEqual(opts.length, 3);
});

test('amount shows extra option for value > 3', function () {
    var opts = LW.getOptionsForStep('amount', 5);
    assert.strictEqual(opts.length, 4);
    assert.strictEqual(opts[3].value, 5);
});

test('cost shows 1-9', function () {
    var opts = LW.getOptionsForStep('cost', 3);
    assert.strictEqual(opts.length, 9);
});

test('cost shows extra for value > 9', function () {
    var opts = LW.getOptionsForStep('cost', 12);
    assert.strictEqual(opts.length, 10);
});

test('cost shows extra for value 0', function () {
    var opts = LW.getOptionsForStep('cost', 0);
    assert.strictEqual(opts.length, 10);
});

// ═══════════════════════════════════════════════════════════════
// getAmountPrompt
// ═══════════════════════════════════════════════════════════════

console.log('--- getAmountPrompt tests ---');

test('ramp land_ramp prompt', function () {
    var p = LW.getAmountPrompt('ramp', {rampType: 'land_ramp'});
    assert.ok(p.indexOf('lands') >= 0);
});

test('ramp cost_reducer prompt', function () {
    var p = LW.getAmountPrompt('ramp', {rampType: 'cost_reducer'});
    assert.ok(p.indexOf('reduction') >= 0);
});

test('ramp mana_rock prompt', function () {
    var p = LW.getAmountPrompt('ramp', {rampType: 'mana_rock'});
    assert.ok(p.indexOf('mana') >= 0);
});

test('draw prompt', function () {
    var p = LW.getAmountPrompt('draw', {});
    assert.ok(p.indexOf('cards drawn') >= 0);
});

test('discard prompt', function () {
    var p = LW.getAmountPrompt('discard', {});
    assert.ok(p.indexOf('discard') >= 0);
});

// ═══════════════════════════════════════════════════════════════
// Summary
// ═══════════════════════════════════════════════════════════════

console.log('\n=== Results: ' + passed + ' passed, ' + failed + ' failed ===');
if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach(function (f) {
        console.log('  ' + f.name + ': ' + f.error.message);
    });
    process.exit(1);
}

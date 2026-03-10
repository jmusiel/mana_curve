/**
 * Card Labeler Wizard — pure logic module.
 *
 * Extracted from simulate.html so the decision-tree state machine,
 * category builders, and annotation decoder can be unit-tested
 * independently of the DOM.
 *
 * Browser: loaded via <script> before the IIFE in simulate.html;
 *          exposes window.LabelerWizard.
 * Node:    require('./labeler_wizard.js') returns the same object.
 */
(function (root) {
    'use strict';

    // ── Step definitions ────────────────────────────────────────────
    var STEP_DEFS = {
        classify:     { prompt: 'What does this card do?', options: [
                          {value: 'draw', label: 'Draw'}, {value: 'ramp', label: 'Ramp'},
                          {value: 'both', label: 'Both'}, {value: 'neither', label: 'Neither', style: 'secondary'}
                      ]},
        ramp:         { prompt: 'What kind of ramp?', options: [
                          {value: 'mana_rock', label: 'Mana Rock'}, {value: 'mana_dork', label: 'Mana Dork'},
                          {value: 'land_ramp', label: 'Land Ramp'}, {value: 'ritual', label: 'Ritual'},
                          {value: 'cost_reducer', label: 'Cost Reducer'}
                      ]},
        tempo:        { prompt: 'Does it enter tapped or untapped?', options: [
                          {value: 'tapped', label: 'Tapped'}, {value: 'untapped', label: 'Untapped'}
                      ]},
        'spell-type': { prompt: 'What spell type does it reduce?', options: [
                          {value: 'creature', label: 'Creature'}, {value: 'enchantment', label: 'Enchantment'},
                          {value: 'nonpermanent', label: 'Nonpermanent'}, {value: 'permanent', label: 'Permanent'},
                          {value: 'spell', label: 'Spell'}
                      ]},
        'draw-type':  { prompt: 'Does this card also discard?', options: [
                          {value: 'draw_only', label: 'Draw Only'}, {value: 'draw_discard', label: 'Draw + Discard (Looting)'}
                      ]},
        'draw-timing':{ prompt: 'When does it draw?', options: [
                          {value: 'immediate', label: 'Immediate (ETB)'}, {value: 'per_turn', label: 'Per Turn'},
                          {value: 'per_cast', label: 'Per Cast'}
                      ]},
        trigger:      { prompt: 'What triggers the draw?', options: [
                          {value: 'creature', label: 'Creature'}, {value: 'spell', label: 'Spell'},
                          {value: 'enchantment', label: 'Enchantment'}, {value: 'land', label: 'Land'},
                          {value: 'artifact', label: 'Artifact'}, {value: 'nonpermanent', label: 'Nonpermanent'}
                      ]},
        amount:       { prompt: 'How many?', type: 'amount' },
        cost:         { prompt: 'How much does this card cost?', type: 'cost' }
    };

    // ── Helpers ─────────────────────────────────────────────────────

    function labelFor(stepId, value) {
        var def = STEP_DEFS[stepId];
        if (def && def.options) {
            var opt = def.options.find(function (o) { return o.value === value; });
            if (opt) return opt.label;
        }
        return String(value);
    }

    function promptFor(stepId, logEntry) {
        if (logEntry && logEntry.prompt) return logEntry.prompt;
        return STEP_DEFS[stepId] ? STEP_DEFS[stepId].prompt : stepId;
    }

    function getFirstStep() {
        return 'cost';
    }

    function getAmountPrompt(amountContext, state) {
        if (amountContext === 'ramp') {
            if (state.rampType === 'land_ramp') return 'How many lands does it fetch?';
            if (state.rampType === 'cost_reducer') return 'How much cost reduction?';
            return 'How much mana does it produce?';
        }
        if (amountContext === 'draw') return 'How many cards drawn?';
        if (amountContext === 'discard') return 'How many cards discarded?';
        return 'How many?';
    }

    // ── State machine ───────────────────────────────────────────────

    /**
     * Apply a single decision to `ctx` (state + amountContext) and
     * return the next step ID ('_done' when tree is complete).
     *
     * `ctx` is mutated in place: { state: {}, amountContext: '' }
     */
    function applyDecision(stepId, value, ctx) {
        var state = ctx.state;

        if (stepId === 'cost') {
            state.costOverride = parseInt(value, 10);
            return 'classify';
        }
        if (stepId === 'classify') {
            if (value === 'draw')    { state.mainType = 'draw'; return 'draw-type'; }
            if (value === 'ramp')    { state.mainType = 'ramp'; return 'ramp'; }
            if (value === 'both')    { state.mainType = 'both'; return 'ramp'; }
            state.mainType = 'neither';
            return '_done';
        }
        if (stepId === 'ramp') {
            state.rampType = value;
            if (value === 'cost_reducer') return 'spell-type';
            ctx.amountContext = 'ramp';
            return 'amount';
        }
        if (stepId === 'spell-type') {
            state.spellType = value;
            ctx.amountContext = 'ramp';
            return 'amount';
        }
        if (stepId === 'amount') {
            var num = parseInt(value, 10) || 1;
            if (ctx.amountContext === 'ramp') {
                state.rampAmount = num;
                if (state.rampType === 'mana_rock' || state.rampType === 'land_ramp') return 'tempo';
                if (state.rampType === 'mana_dork') {
                    state.tempo = 'summoning_sick';
                    return _finishRampOrContinue(state);
                }
                return _finishRampOrContinue(state);
            }
            if (ctx.amountContext === 'draw') {
                state.drawAmount = num;
                if (state.drawType === 'draw_discard') {
                    ctx.amountContext = 'discard';
                    return 'amount';
                }
                return '_done';
            }
            if (ctx.amountContext === 'discard') {
                state.discardAmount = num;
                return '_done';
            }
        }
        if (stepId === 'tempo') {
            state.tempo = value;
            return _finishRampOrContinue(state);
        }
        if (stepId === 'draw-type') {
            state.drawType = value;
            return 'draw-timing';
        }
        if (stepId === 'draw-timing') {
            state.drawTiming = value;
            if (value === 'per_cast') return 'trigger';
            ctx.amountContext = 'draw';
            return 'amount';
        }
        if (stepId === 'trigger') {
            state.trigger = value;
            ctx.amountContext = 'draw';
            return 'amount';
        }
        return '_done';
    }

    function _finishRampOrContinue(state) {
        if (state.mainType === 'both') return 'draw-type';
        return '_done';
    }

    // ── Category builders ───────────────────────────────────────────

    function buildRampCategories(state, cats) {
        if (state.rampType === 'mana_rock' || state.rampType === 'mana_dork') {
            var cat = {category: 'ramp', immediate: false, producer: {mana_amount: state.rampAmount || 1}};
            if (state.tempo === 'tapped') cat.producer.tempo = 'tapped';
            else if (state.tempo === 'summoning_sick') cat.producer.tempo = 'summoning_sick';
            else cat.producer.tempo = 'untapped';
            cats.push(cat);
        } else if (state.rampType === 'ritual') {
            cats.push({category: 'ramp', immediate: true, producer: {mana_amount: state.rampAmount || 1}});
        } else if (state.rampType === 'land_ramp') {
            cats.push({category: 'ramp', immediate: true, land_to_battlefield: {count: state.rampAmount || 1, tempo: state.tempo || 'tapped'}});
        } else if (state.rampType === 'cost_reducer') {
            cats.push({category: 'ramp', immediate: false, reducer: {spell_type: state.spellType || 'creature', amount: state.rampAmount || 1}});
        }
    }

    function buildDrawCategories(state, cats) {
        if (state.drawTiming === 'immediate') {
            cats.push({category: 'draw', immediate: true, amount: state.drawAmount || 1});
        } else if (state.drawTiming === 'per_turn') {
            cats.push({category: 'draw', immediate: false, per_turn: {amount: state.drawAmount || 1}});
        } else if (state.drawTiming === 'per_cast') {
            cats.push({category: 'draw', immediate: false, per_cast: {amount: state.drawAmount || 1, trigger: state.trigger || 'spell'}});
        }
        if (state.drawType === 'draw_discard' && state.discardAmount) {
            cats.push({category: 'discard', amount: state.discardAmount});
        }
    }

    function buildCategories(state) {
        var cats = [];
        if (state.mainType === 'ramp') {
            buildRampCategories(state, cats);
        } else if (state.mainType === 'draw') {
            buildDrawCategories(state, cats);
        } else if (state.mainType === 'both') {
            buildRampCategories(state, cats);
            buildDrawCategories(state, cats);
        }
        return cats;
    }

    /**
     * Validate that built categories conform to basic schema expectations.
     * Returns an array of error strings (empty = valid).
     */
    function validateCategories(categories) {
        var errors = [];
        var validCats = {ramp: true, draw: true, discard: true, land: true};
        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            if (!cat.category || !validCats[cat.category]) {
                errors.push('Invalid category: ' + (cat.category || '(empty)'));
                continue;
            }
            if (cat.category === 'ramp') {
                if (!cat.producer && !cat.land_to_battlefield && !cat.reducer) {
                    errors.push('Ramp category missing producer, land_to_battlefield, or reducer');
                }
            }
            if (cat.category === 'draw') {
                if (cat.immediate && (cat.amount === undefined || cat.amount === null)) {
                    errors.push('Immediate draw missing amount');
                }
                if (!cat.immediate && !cat.per_turn && !cat.per_cast) {
                    errors.push('Non-immediate draw missing per_turn or per_cast');
                }
            }
            if (cat.category === 'discard') {
                if (cat.amount === undefined || cat.amount === null) {
                    errors.push('Discard category missing amount');
                }
            }
        }
        return errors;
    }

    // ── Annotation decoder ──────────────────────────────────────────

    /**
     * Decode a prior annotation into a decision log array.
     *
     * @param {object} annotation  - The saved annotation ({categories, override_cmc, ...})
     * @param {object} card        - The card dict ({cmc, ...})
     * @returns {Array} decision log entries
     */
    function decodeAnnotation(annotation, card) {
        var log = [];
        if (!annotation || !annotation.categories) return log;
        var cats = annotation.categories;

        // Cost step
        if (card) {
            var costVal = (annotation.override_cmc !== undefined && annotation.override_cmc !== null)
                ? annotation.override_cmc : (card.cmc || 0);
            log.push({stepId: 'cost', prompt: STEP_DEFS.cost.prompt, chosenValue: costVal, chosenLabel: String(costVal)});
        }

        if (cats.length === 0) {
            // "neither" — add classify step so the log is complete
            log.push({stepId: 'classify', prompt: STEP_DEFS.classify.prompt, chosenValue: 'neither', chosenLabel: 'Neither'});
            return log;
        }

        var rampCat = cats.find(function (c) { return c.category === 'ramp'; });
        var drawCat = cats.find(function (c) { return c.category === 'draw'; });
        var discardCat = cats.find(function (c) { return c.category === 'discard'; });

        var classifyValue;
        if (rampCat && drawCat) classifyValue = 'both';
        else if (rampCat) classifyValue = 'ramp';
        else if (drawCat) classifyValue = 'draw';
        else return log;

        log.push({stepId: 'classify', prompt: STEP_DEFS.classify.prompt, chosenValue: classifyValue, chosenLabel: labelFor('classify', classifyValue)});

        if (rampCat) {
            var rampType;
            if (rampCat.reducer) rampType = 'cost_reducer';
            else if (rampCat.land_to_battlefield) rampType = 'land_ramp';
            else if (rampCat.immediate && rampCat.producer) rampType = 'ritual';
            else if (rampCat.producer) {
                rampType = (rampCat.producer.tempo === 'summoning_sick') ? 'mana_dork' : 'mana_rock';
            }

            if (rampType) {
                log.push({stepId: 'ramp', prompt: STEP_DEFS.ramp.prompt, chosenValue: rampType, chosenLabel: labelFor('ramp', rampType)});

                if (rampType === 'cost_reducer') {
                    var spellType = rampCat.reducer.spell_type || 'creature';
                    log.push({stepId: 'spell-type', prompt: STEP_DEFS['spell-type'].prompt, chosenValue: spellType, chosenLabel: labelFor('spell-type', spellType)});
                    var amt = rampCat.reducer.amount || 1;
                    log.push({stepId: 'amount', prompt: 'How much cost reduction?', chosenValue: amt, chosenLabel: String(amt)});
                } else if (rampType === 'land_ramp') {
                    var count = rampCat.land_to_battlefield.count || 1;
                    log.push({stepId: 'amount', prompt: 'How many lands does it fetch?', chosenValue: count, chosenLabel: String(count)});
                    var tempo = rampCat.land_to_battlefield.tempo || 'tapped';
                    log.push({stepId: 'tempo', prompt: STEP_DEFS.tempo.prompt, chosenValue: tempo, chosenLabel: labelFor('tempo', tempo)});
                } else if (rampType === 'mana_rock') {
                    var manaAmt = rampCat.producer.mana_amount || 1;
                    log.push({stepId: 'amount', prompt: 'How much mana does it produce?', chosenValue: manaAmt, chosenLabel: String(manaAmt)});
                    var tempoVal = rampCat.producer.tempo === 'tapped' ? 'tapped' : 'untapped';
                    log.push({stepId: 'tempo', prompt: STEP_DEFS.tempo.prompt, chosenValue: tempoVal, chosenLabel: labelFor('tempo', tempoVal)});
                } else if (rampType === 'mana_dork') {
                    var dorkAmt = rampCat.producer.mana_amount || 1;
                    log.push({stepId: 'amount', prompt: 'How much mana does it produce?', chosenValue: dorkAmt, chosenLabel: String(dorkAmt)});
                } else if (rampType === 'ritual') {
                    var ritAmt = rampCat.producer.mana_amount || 1;
                    log.push({stepId: 'amount', prompt: 'How much mana does it produce?', chosenValue: ritAmt, chosenLabel: String(ritAmt)});
                }
            }
        }

        if (drawCat) {
            var drawType = discardCat ? 'draw_discard' : 'draw_only';
            log.push({stepId: 'draw-type', prompt: STEP_DEFS['draw-type'].prompt, chosenValue: drawType, chosenLabel: labelFor('draw-type', drawType)});

            var timing;
            if (drawCat.immediate) timing = 'immediate';
            else if (drawCat.per_turn) timing = 'per_turn';
            else if (drawCat.per_cast) timing = 'per_cast';

            if (timing) {
                log.push({stepId: 'draw-timing', prompt: STEP_DEFS['draw-timing'].prompt, chosenValue: timing, chosenLabel: labelFor('draw-timing', timing)});

                if (timing === 'per_cast') {
                    var trigger = drawCat.per_cast.trigger || 'spell';
                    log.push({stepId: 'trigger', prompt: STEP_DEFS.trigger.prompt, chosenValue: trigger, chosenLabel: labelFor('trigger', trigger)});
                }

                var drawAmount;
                if (timing === 'immediate') drawAmount = drawCat.amount || 1;
                else if (timing === 'per_turn') drawAmount = drawCat.per_turn.amount || 1;
                else if (timing === 'per_cast') drawAmount = drawCat.per_cast.amount || 1;
                log.push({stepId: 'amount', prompt: 'How many cards drawn?', chosenValue: drawAmount, chosenLabel: String(drawAmount)});

                if (discardCat) {
                    var discAmt = discardCat.amount || 1;
                    log.push({stepId: 'amount', prompt: 'How many cards discarded?', chosenValue: discAmt, chosenLabel: String(discAmt)});
                }
            }
        }

        return log;
    }

    // ── Describe annotation (human-readable) ────────────────────────

    function describePriorAnnotation(annotation) {
        if (!annotation || !annotation.categories) return 'No effects';
        var cats = annotation.categories;
        if (cats.length === 0) return 'No effects';
        var parts = cats.map(function (c) {
            if (c.category === 'ramp') {
                if (c.producer) return 'Ramp: produces ' + (c.producer.mana_amount || 1) + ' mana' + (c.immediate ? ' (immediate)' : '');
                if (c.land_to_battlefield) return 'Ramp: fetch ' + (c.land_to_battlefield.count || 1) + ' land(s) ' + (c.land_to_battlefield.tempo || 'tapped');
                if (c.reducer) return 'Ramp: reduce ' + (c.reducer.spell_type || 'spell') + ' cost by ' + (c.reducer.amount || 1);
                return 'Ramp';
            }
            if (c.category === 'draw') {
                if (c.immediate) return 'Draw ' + (c.amount || 1) + ' card(s)';
                if (c.per_turn) return 'Draw ' + (c.per_turn.amount || 1) + ' per turn';
                if (c.per_cast) return 'Draw ' + (c.per_cast.amount || 1) + ' per ' + (c.per_cast.trigger || 'spell') + ' cast';
                return 'Draw';
            }
            if (c.category === 'discard') return 'Discard ' + (c.amount || 1);
            return c.category;
        });
        return parts.join(', ');
    }

    // ── Flowchart option helpers ────────────────────────────────────

    function getOptionsForStep(stepId, chosenValue) {
        var def = STEP_DEFS[stepId];
        if (def && def.options) return def.options;
        if (stepId === 'amount') {
            var opts = [{value: 1, label: '1'}, {value: 2, label: '2'}, {value: 3, label: '3'}];
            var num = parseInt(chosenValue, 10) || 1;
            if (num > 3) opts.push({value: num, label: String(num)});
            return opts;
        }
        if (stepId === 'cost') {
            var costOpts = [];
            for (var i = 1; i <= 9; i++) costOpts.push({value: i, label: String(i)});
            var cv = parseInt(chosenValue, 10);
            if (cv > 9 || cv === 0) costOpts.push({value: cv, label: String(cv)});
            return costOpts;
        }
        return [{value: chosenValue, label: String(chosenValue)}];
    }

    /**
     * Replay a sequence of decisions from scratch and return the final context.
     *
     * @param {Array} decisions - [{stepId, chosenValue}, ...]
     * @returns {{state: object, amountContext: string, nextStep: string}}
     */
    function replayDecisions(decisions) {
        var ctx = {state: {}, amountContext: ''};
        var nextStep = getFirstStep();
        for (var i = 0; i < decisions.length; i++) {
            nextStep = applyDecision(decisions[i].stepId, decisions[i].chosenValue, ctx);
        }
        return {state: ctx.state, amountContext: ctx.amountContext, nextStep: nextStep};
    }

    // ── Public API ──────────────────────────────────────────────────

    var LabelerWizard = {
        STEP_DEFS: STEP_DEFS,
        labelFor: labelFor,
        promptFor: promptFor,
        getFirstStep: getFirstStep,
        getAmountPrompt: getAmountPrompt,
        applyDecision: applyDecision,
        buildCategories: buildCategories,
        buildRampCategories: buildRampCategories,
        buildDrawCategories: buildDrawCategories,
        validateCategories: validateCategories,
        decodeAnnotation: decodeAnnotation,
        describePriorAnnotation: describePriorAnnotation,
        getOptionsForStep: getOptionsForStep,
        replayDecisions: replayDecisions
    };

    // UMD export
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = LabelerWizard;
    } else {
        root.LabelerWizard = LabelerWizard;
    }

})(typeof window !== 'undefined' ? window : this);

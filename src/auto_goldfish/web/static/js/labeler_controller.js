/**
 * Shared DOM controller for the card labeler wizard.
 *
 * LabelerWizard owns the pure decision tree. This controller owns browser
 * state, rendering, rewinds, and option clicks so every page gets the same
 * behavior.
 */
(function(root) {
    'use strict';

    function byId(id) {
        return typeof id === 'string' ? document.getElementById(id) : id;
    }

    function create(options) {
        options = options || {};
        var LW = options.wizard || root.LabelerWizard;
        var flowchartEl = byId(options.flowchart);
        var submitBtn = byId(options.submitButton);
        var undoBtn = byId(options.undoButton);
        var ctx = {state: {}, amountContext: ''};
        var decisionLog = [];
        var activeStep = LW.getFirstStep();
        var card = null;

        function notify() {
            if (typeof options.onStateChange === 'function') {
                options.onStateChange(api);
            }
        }

        function render() {
            if (!flowchartEl) return;
            flowchartEl.innerHTML = '';

            decisionLog.forEach(function(entry, idx) {
                var node = document.createElement('div');
                node.className = 'flowchart-node flowchart-node-answered';

                var prompt = document.createElement('span');
                prompt.className = 'flowchart-prompt';
                prompt.textContent = LW.promptFor(entry.stepId, entry);
                node.appendChild(prompt);

                var btns = document.createElement('span');
                btns.className = 'flowchart-options';
                LW.getOptionsForStep(entry.stepId, entry.chosenValue).forEach(function(opt) {
                    var chip = document.createElement('button');
                    chip.type = 'button';
                    if (String(opt.value) === String(entry.chosenValue)) {
                        chip.className = 'flowchart-answer';
                        chip.title = 'Click to change from here';
                        chip.addEventListener('click', function() { rewindTo(idx); });
                    } else {
                        chip.className = 'flowchart-answer flowchart-answer-alt';
                        chip.title = 'Switch to ' + opt.label;
                        chip.addEventListener('click', function() { rewindAndChoose(idx, opt.value); });
                    }
                    chip.textContent = opt.label;
                    btns.appendChild(chip);
                });
                node.appendChild(btns);
                flowchartEl.appendChild(node);
            });

            if (submitBtn) {
                submitBtn.style.display = (!activeStep && decisionLog.length > 0) ? '' : 'none';
            }
            if (undoBtn) {
                undoBtn.style.display = decisionLog.length > 0 ? '' : 'none';
            }

            if (activeStep) {
                var def = LW.STEP_DEFS[activeStep];
                if (def) {
                    var activeNode = document.createElement('div');
                    activeNode.className = 'flowchart-node flowchart-node-active';
                    if (def.type === 'amount') {
                        renderAmountNode(activeNode);
                    } else if (def.type === 'cost') {
                        renderCostNode(activeNode);
                    } else if (def.options) {
                        renderOptionsNode(activeNode, def);
                    }
                    flowchartEl.appendChild(activeNode);
                }
            }

            notify();
            if (typeof options.onRender === 'function') {
                options.onRender(api);
            }
        }

        function renderPrompt(node, text) {
            var p = document.createElement('p');
            p.className = 'labeler-prompt';
            p.textContent = text;
            node.appendChild(p);
        }

        function makeChip(value, label, keyHint) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'flowchart-answer flowchart-answer-alt';
            if (keyHint) {
                var hint = document.createElement('span');
                hint.className = 'flowchart-key-hint';
                hint.textContent = String(keyHint);
                chip.appendChild(hint);
            }
            chip.appendChild(document.createTextNode(String(label)));
            chip.addEventListener('click', function() { choose(value); });
            return chip;
        }

        function renderAmountNode(node) {
            renderPrompt(node, LW.getAmountPrompt(ctx.amountContext, ctx.state));
            var btns = document.createElement('div');
            btns.className = 'flowchart-options';
            [1, 2, 3].forEach(function(n) {
                btns.appendChild(makeChip(n, n, n));
            });

            var custom = document.createElement('span');
            custom.className = 'labeler-custom-amount';
            var input = document.createElement('input');
            input.type = 'number';
            input.min = '1';
            input.max = '20';
            input.value = '4';
            input.style.width = '4rem';
            input.id = options.amountInputId || 'labeler-custom-amount';
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    choose(parseInt(input.value, 10) || 1);
                    input.blur();
                }
            });
            custom.appendChild(input);
            var ok = document.createElement('button');
            ok.type = 'button';
            ok.className = 'btn btn-secondary btn-sm';
            ok.textContent = 'OK';
            ok.addEventListener('click', function() { choose(parseInt(input.value, 10) || 1); });
            custom.appendChild(ok);
            btns.appendChild(custom);
            node.appendChild(btns);
        }

        function renderCostNode(node) {
            renderPrompt(node, LW.STEP_DEFS.cost.prompt);
            var btns = document.createElement('div');
            btns.className = 'flowchart-options';
            for (var n = 1; n <= 9; n++) {
                btns.appendChild(makeChip(n, n, n));
            }

            var custom = document.createElement('span');
            custom.className = 'labeler-custom-amount';
            var zeroHint = document.createElement('span');
            zeroHint.className = 'flowchart-key-hint';
            zeroHint.textContent = '0';
            custom.appendChild(zeroHint);
            var input = document.createElement('input');
            input.type = 'number';
            input.min = '0';
            input.max = '20';
            input.placeholder = '#';
            input.style.width = '3rem';
            input.id = options.costInputId || 'labeler-cost-custom';
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === 'ArrowDown') {
                    e.preventDefault();
                    var val = parseInt(input.value, 10);
                    if (!isNaN(val) && val >= 0) choose(val);
                    input.blur();
                }
            });
            custom.appendChild(input);
            var ok = document.createElement('button');
            ok.type = 'button';
            ok.className = 'btn btn-secondary btn-sm';
            ok.textContent = 'OK';
            ok.addEventListener('click', function() {
                var val = parseInt(input.value, 10);
                if (!isNaN(val) && val >= 0) choose(val);
            });
            custom.appendChild(ok);
            btns.appendChild(custom);
            node.appendChild(btns);
        }

        function renderOptionsNode(node, def) {
            renderPrompt(node, def.prompt);
            var btns = document.createElement('div');
            btns.className = 'flowchart-options';
            def.options.forEach(function(opt, idx) {
                btns.appendChild(makeChip(opt.value, opt.label, idx + 1));
            });
            node.appendChild(btns);
        }

        function replay(log) {
            ctx = {state: {}, amountContext: ''};
            var next = LW.getFirstStep();
            log.forEach(function(entry) {
                next = LW.applyDecision(entry.stepId, entry.chosenValue, ctx);
            });
            return next;
        }

        function rewindTo(index) {
            decisionLog = decisionLog.slice(0, index);
            activeStep = replay(decisionLog);
            render();
        }

        function rewindAndChoose(index, value) {
            decisionLog = decisionLog.slice(0, index);
            activeStep = replay(decisionLog);
            choose(value);
        }

        function choose(value) {
            if (!activeStep) return;
            var curStep = activeStep;
            var prompt = curStep === 'amount'
                ? LW.getAmountPrompt(ctx.amountContext, ctx.state)
                : LW.STEP_DEFS[curStep].prompt;
            var label = LW.labelFor(curStep, value);
            var nextStep = LW.applyDecision(curStep, value, ctx);
            decisionLog.push({
                stepId: curStep,
                prompt: prompt,
                chosenValue: value,
                chosenLabel: label,
            });

            if (nextStep === '_done') {
                if (ctx.state.mainType === 'neither' && typeof options.onNeitherComplete === 'function') {
                    if (options.onNeitherComplete(api)) {
                        notify();
                        return;
                    }
                }
                activeStep = null;
            } else {
                activeStep = nextStep;
            }
            render();
        }

        function undo() {
            if (decisionLog.length > 0) rewindTo(decisionLog.length - 1);
        }

        function setFromAnnotation(nextCard, annotation, loadOptions) {
            loadOptions = loadOptions || {};
            card = nextCard || null;
            ctx = {state: {}, amountContext: ''};
            decisionLog = [];
            var hasCategories = annotation && annotation.categories;
            var shouldDecode = hasCategories && (
                loadOptions.decodeEmptyAnnotation || (annotation.categories || []).length > 0
            );
            if (shouldDecode) {
                decisionLog = LW.decodeAnnotation(annotation, card);
                var result = LW.replayDecisions(decisionLog);
                ctx.state = result.state;
                ctx.amountContext = result.amountContext;
                activeStep = null;
            } else {
                var costVal = card && card.cmc != null ? card.cmc : 0;
                decisionLog.push({
                    stepId: 'cost',
                    prompt: LW.STEP_DEFS.cost.prompt,
                    chosenValue: costVal,
                    chosenLabel: String(costVal),
                });
                LW.applyDecision('cost', costVal, ctx);
                activeStep = 'classify';
            }
            render();
        }

        function getEffectData() {
            var effectData = {categories: LW.buildCategories(ctx.state)};
            if (ctx.state.costOverride !== undefined && ctx.state.costOverride !== null) {
                effectData.override_cmc = ctx.state.costOverride;
            }
            return effectData;
        }

        var api = {
            render: render,
            choose: choose,
            undo: undo,
            rewindTo: rewindTo,
            rewindAndChoose: rewindAndChoose,
            setFromAnnotation: setFromAnnotation,
            getContext: function() { return ctx; },
            getDecisionLog: function() { return decisionLog; },
            getActiveStep: function() { return activeStep; },
            isComplete: function() { return !activeStep && decisionLog.length > 0; },
            getEffectData: getEffectData,
            getCard: function() { return card; },
        };

        notify();
        return api;
    }

    var LabelerController = {create: create};
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = LabelerController;
    } else {
        root.LabelerController = LabelerController;
    }
})(typeof window !== 'undefined' ? window : this);

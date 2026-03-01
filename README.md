# mana_curve

A Magic: The Gathering commander deck simulation tool. Runs "goldfishing" simulations (playing games without an opponent) to evaluate deck performance, mana curves, and consistency metrics across thousands of games.

## Features

- **Goldfishing engine** -- simulates drawing, mulligans, land drops, and spell casting over N turns
- **Data-driven card effects** -- 118 cards with special abilities (ramp, draw, cost reduction, tutors) defined as composable effects. Adding a new card is a single `register()` call in `effects/card_database.py`
- **Archidekt integration** -- pull decklists directly from Archidekt URLs via the API
- **Land count sweeping** -- test a range of land counts and compare EV, consistency, bad turns, and percentile distributions
- **Extensible metrics** -- register custom metric functions on top of the built-in ones (mean mana, consistency, bad turns, etc.)
- **Reports** -- generates text reports with per-bucket game stats and mana curve scatter plots (PNG)

## Setup

Requires Python 3.11+. Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync --extra dev
```

Or install in editable mode:

```bash
uv pip install -e ".[dev]"
```

## Usage

### CLI

```bash
# Run with a saved deck JSON
.venv/bin/python -m mana_curve.cli.main --deck_name vren --deck_url https://archidekt.com/decks/19226307/vrens_murine_marauders

# Sweep land counts 36-39, 10 turns, 10k sims
.venv/bin/python -m mana_curve.cli.main --deck_name vren --min_lands 36 --max_lands 39 --turns 10 --sims 10000

# See all options
.venv/bin/python -m mana_curve.cli.main --help
```

### As a library

```python
from mana_curve.decklist.loader import load_decklist
from mana_curve.engine.goldfisher import Goldfisher

deck = load_decklist("vren")
gf = Goldfisher(deck, turns=10, sims=1000)
result = gf.simulate()

print(f"Mean mana spent: {result.mean_mana:.1f}")
print(f"Consistency: {result.consistency:.3f}")
print(f"Bad turns: {result.mean_bad_turns:.2f}")
```

### Adding a new card

All card effects live in `src/mana_curve/effects/card_database.py`. No subclasses needed:

```python
# Single mana producer
reg.register("My New Rock", CardEffects(on_play=[ProduceMana(1)], ramp=True))

# Multi-effect card (draws on creature cast + produces mana)
reg.register("My Engine", CardEffects(
    cast_trigger=[PerCastDraw(creature=1)],
    on_play=[ProduceMana(2)],
    priority=1,
))
```

## Project Structure

```
src/mana_curve/
├── models/          # Card dataclass, GameState dataclass
├── effects/         # Effect protocols, registry, builtin effects, card database
├── engine/          # Goldfisher simulation, mana calculation, mulligan strategy
├── metrics/         # MetricsCollector, built-in metrics, aggregation, reporting
├── decklist/        # JSON loader, Archidekt API, deck builder
└── cli/             # CLI entry point

tests/
├── unit/            # 9 test files covering all modules
└── integration/     # Goldfisher end-to-end tests
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--deck_name` | `vren` | Name used for saving/loading deck JSON |
| `--deck_url` | — | Archidekt deck URL (fetches and caches) |
| `--turns` | `10` | Turns per simulated game |
| `--sims` | `10000` | Number of games to simulate |
| `--min_lands` | `36` | Start of land count sweep |
| `--max_lands` | `39` | End of land count sweep |
| `--cuts` | — | Card names to cut when adding lands |
| `--record_results` | `quartile` | Recording granularity (`centile`, `decile`, `quartile`) |
| `--verbose` | off | Print every game log |

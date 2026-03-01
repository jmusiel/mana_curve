"""Card effects database -- all card-to-effect mappings in one place.

Adding a new card = one ``register`` call, no new classes needed.
"""

from __future__ import annotations

from .builtin import (
    CryptolithRitesMana,
    DrawCards,
    DrawDiscard,
    EnchantmentSanctumMana,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
    ScalingMana,
    TutorToHand,
)
from .registry import CardEffects, EffectRegistry


def build_default_registry() -> EffectRegistry:
    """Build and return the default card effects registry."""
    reg = EffectRegistry()

    # -----------------------------------------------------------------------
    # Mana Producers (fixed amount)
    # -----------------------------------------------------------------------
    reg.register_many(
        [
            "Arcane Signet",
            "Fellwar Stone",
            "Sakura-Tribe Elder",
            "Incubation Druid",
            "Commander's Sphere",
            "Orzhov Signet",
            "Solemn Simulacrum",
            "Claim Jumper",
            "Talisman of Hierarchy",
            "Deep Gnome Terramancer",
            "Cultivate",
            "Utopia Sprawl",
            "Wild Growth",
            "Fertile Ground",
            "Wolfwillow Haven",
            "Kodama's Reach",
            "Farseek",
        ],
        CardEffects(on_play=[ProduceMana(1)], ramp=True),
    )

    reg.register_many(
        [
            "Sol Ring",
            "Relic of Sauron",
            "Rishkar, Peema Renegade",
            "Katilda, Dawnhart Prime",
            "Overgrowth",
        ],
        CardEffects(on_play=[ProduceMana(2)], ramp=True),
    )

    reg.register(
        "Open the Way",
        CardEffects(on_play=[ProduceMana(3)], ramp=True),
    )

    # -----------------------------------------------------------------------
    # Scaling Mana Producers (gain mana each turn)
    # -----------------------------------------------------------------------
    reg.register_many(
        [
            "As Foretold",
            "Séance Board",
            "Smothering Tithe",
            "Gyre Sage",
            "Kami of Whispered Hopes",
            "Heronblade Elite",
            "Kodama of the West Tree",
        ],
        CardEffects(per_turn=[ScalingMana(1)], ramp=True, priority=2),
    )

    # -----------------------------------------------------------------------
    # Cryptolith Rite effects (tap creatures for mana)
    # -----------------------------------------------------------------------
    reg.register_many(
        [
            "Gemhide Sliver",
            "Enduring Vitality",
            "Cryptolith Rite",
            "Manaweft Sliver",
        ],
        CardEffects(mana_function=[CryptolithRitesMana()], ramp=True, priority=2),
    )

    # -----------------------------------------------------------------------
    # Sanctum effects (mana from enchantments)
    # -----------------------------------------------------------------------
    reg.register_many(
        [
            "Serra's Sanctum",
            "Sanctum Weaver",
        ],
        CardEffects(
            mana_function=[EnchantmentSanctumMana()],
            priority=2,
            extra_types=["artifact"],  # Serra's Sanctum is treated as an artifact for simulation
        ),
    )

    # -----------------------------------------------------------------------
    # Cost Reducers
    # -----------------------------------------------------------------------
    reg.register_many(
        ["Thunderclap Drake", "Case of the Ransacked Lab"],
        CardEffects(on_play=[ReduceCost(nonpermanent=1)], ramp=True, priority=2),
    )

    reg.register_many(
        ["Hamza, Guardian of Arashin", "Umori, the Collector"],
        CardEffects(on_play=[ReduceCost(creature=1)], ramp=True, priority=2),
    )

    reg.register_many(
        ["Jukai Naturalist", "Inquisitive Glimmer"],
        CardEffects(on_play=[ReduceCost(enchantment=1)], ramp=True, priority=2),
    )

    # -----------------------------------------------------------------------
    # Tutors
    # -----------------------------------------------------------------------
    _green_tutor_targets = [
        "Gemhide Sliver",
        "Manaweft Sliver",
        "Enduring Vitality",
        "Sanctum Weaver",
        "Argothian Enchantress",
        "Sythis, Harvest's Hand",
        "Setessan Champion",
        "Satyr Enchanter",
        "Verduran Enchantress",
        "Eidolon of Blossoms",
    ]

    reg.register_many(
        ["Green Sun's Zenith", "Finale of Devastation"],
        CardEffects(on_play=[TutorToHand(_green_tutor_targets)], ramp=True, priority=3),
    )

    # Land tutors (search for Serra's Sanctum)
    reg.register(
        "Tolaria West",
        CardEffects(
            on_play=[TutorToHand(["Serra's Sanctum"])],
            ramp=True,
            priority=3,
            is_land_tutor=True,
            extra_types=["sorcery"],
            override_cmc=3,
            tapped=True,
        ),
    )

    reg.register(
        "Urza's Cave",
        CardEffects(
            on_play=[TutorToHand(["Serra's Sanctum"])],
            ramp=True,
            priority=3,
            is_land_tutor=True,
            extra_types=["sorcery"],
            override_cmc=3,
        ),
    )

    # -----------------------------------------------------------------------
    # Immediate Draw
    # -----------------------------------------------------------------------
    _draw_1 = ["Archivist of Oghma", "Growth Spiral", "Explore", "Mulch"]
    _draw_2 = ["Flame of Anor", "Plumb the Forbidden", "Diresight", "Read the Bones"]
    _draw_3 = [
        "Manifold Insights",
        "Mystic Confluence",
        "Armorcraft Judge",
        "Inspiring Call",
        "Krav, the Unredeemed",
        "Body Count",
        "Urban Evolution",
    ]
    _draw_4 = ["Rishkar's Expertise"]

    for names, n in [(_draw_1, 1), (_draw_2, 2), (_draw_3, 3), (_draw_4, 4)]:
        reg.register_many(names, CardEffects(on_play=[DrawCards(n)], priority=1))

    # -----------------------------------------------------------------------
    # Draw/Discard
    # -----------------------------------------------------------------------
    _dd_simple_1 = [
        "Frantic Search", "Brainstorm", "Gitaxian Probe", "Gamble",
        "Visions of Beyond", "Mystical Tutor", "See the Truth",
    ]
    reg.register_many(
        _dd_simple_1,
        CardEffects(on_play=[DrawDiscard(first_draw=1)], priority=1),
    )

    reg.register("Fact or Fiction", CardEffects(
        on_play=[DrawDiscard(first_draw=5, discard=2)], priority=1,
    ))
    reg.register("Windfall", CardEffects(
        on_play=[DrawDiscard(discard=100, second_draw=6)], priority=1,
    ))
    reg.register_many(
        ["Unexpected Windfall", "Big Score"],
        CardEffects(on_play=[DrawDiscard(discard=1, second_draw=2, make_treasures=2)], priority=1),
    )
    reg.register("Maestros Charm", CardEffects(
        on_play=[DrawDiscard(first_draw=5, discard=4)], priority=1,
    ))
    reg.register("Picklock Prankster // Free the Fae", CardEffects(
        on_play=[DrawDiscard(first_draw=4, discard=3)], priority=1,
    ))
    reg.register("Consider", CardEffects(
        on_play=[DrawDiscard(first_draw=2, discard=1)], priority=1,
    ))
    reg.register("Thought Scour", CardEffects(
        on_play=[DrawDiscard(first_draw=3, discard=2)], priority=1,
    ))
    reg.register("Faithless Looting", CardEffects(
        on_play=[DrawDiscard(first_draw=2, discard=2)], priority=1,
    ))
    reg.register("Prismari Command", CardEffects(
        on_play=[DrawDiscard(first_draw=2, discard=2, make_treasures=1)], priority=1,
    ))
    reg.register("Deadly Dispute", CardEffects(
        on_play=[DrawDiscard(first_draw=2, make_treasures=1)], priority=1,
    ))

    # -----------------------------------------------------------------------
    # Per-Turn Draw
    # -----------------------------------------------------------------------
    reg.register_many(
        [
            "Black Market Connections",
            "Esper Sentinel",
            "Phyrexian Arena",
            "Ripples of Undeath",
            "Toski, Bearer of Secrets",
            "Leinore, Autumn Sovereign",
            "Compost",
            "Tuvasa the Sunlit",
            "Mystic Remora",
            "Enduring Innocence",
            "Haliya, Guided by Light",
            "Priest of Forgotten Gods",
            "Tocasia's Welcome",
            "Welcoming Vampire",
            "Rumor Gatherer",
            "Morbid Opportunist",
        ],
        CardEffects(per_turn=[PerTurnDraw(1)], priority=1),
    )

    # -----------------------------------------------------------------------
    # Per-Cast Draw
    # -----------------------------------------------------------------------
    reg.register_many(
        ["Archmage Emeritus", "Archmage of Runes"],
        CardEffects(
            cast_trigger=[PerCastDraw(nonpermanent=1)],
            priority=1,
        ),
    )

    # Archmage of Runes also reduces nonpermanent cost
    reg.register(
        "Archmage of Runes",
        CardEffects(
            cast_trigger=[PerCastDraw(nonpermanent=1)],
            on_play=[ReduceCost(nonpermanent=1)],
            priority=1,
        ),
    )

    reg.register(
        "Bolas's Citadel",
        CardEffects(cast_trigger=[PerCastDraw(spell=1)], priority=1),
    )

    reg.register_many(
        [
            "Skullclamp",
            "Beast Whisperer",
            "Guardian Project",
            "Vanquisher's Banner",
            "Tribute to the World Tree",
            "Erebos, Bleak-Hearted",
            "Mentor of the Meek",
        ],
        CardEffects(cast_trigger=[PerCastDraw(creature=1)], priority=1),
    )

    # The Great Henge: creature cast draw + mana production
    reg.register(
        "The Great Henge",
        CardEffects(
            cast_trigger=[PerCastDraw(creature=1)],
            on_play=[ProduceMana(2)],
            priority=1,
        ),
    )

    reg.register_many(
        [
            "Mesa Enchantress",
            "Satyr Enchanter",
            "Enchantress's Presence",
            "Entity Tracker",
            "Eidolon of Blossoms",
            "Setessan Champion",
            "Sythis, Harvest's Hand",
            "Verduran Enchantress",
            "Argothian Enchantress",
        ],
        CardEffects(cast_trigger=[PerCastDraw(enchantment=1)], priority=1),
    )

    # -----------------------------------------------------------------------
    # Special cards
    # -----------------------------------------------------------------------

    # Lórien Revealed: MDFC land that draws 3
    reg.register(
        "Lórien Revealed",
        CardEffects(
            on_play=[DrawCards(3)],
            extra_types=["land"],
            tapped=True,
        ),
    )

    # Cabal Coffers: treated as artifact for simulation
    reg.register(
        "Cabal Coffers",
        CardEffects(extra_types=["artifact"]),
    )

    return reg


# Singleton default registry
DEFAULT_REGISTRY = build_default_registry()

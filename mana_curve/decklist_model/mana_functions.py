

def land_mana(gf):
    return len(gf.lands)

def mana_rocks(gf):
    return gf.mana_production

def cryptolith_rites(gf):
    mana = min(0, gf.creatures_played - gf.tapped_creatures_this_turn)
    gf.tapped_creatures_this_turn = gf.creatures_played
    return mana

def enchantment_sanctums(gf):
    return gf.enchantments_played

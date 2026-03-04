/**
 * DeckStore — localStorage CRUD for user deck data.
 *
 * Each deck is stored as {cards: [...], overrides: {...}, last_accessed: <ms>}.
 * All decks live under a single localStorage key.
 * When storage is full, the least-recently-accessed deck is evicted.
 */
var DeckStore = {
    _key: 'ag_decks',

    _load: function() {
        try {
            return JSON.parse(localStorage.getItem(this._key)) || {};
        } catch (e) {
            return {};
        }
    },

    _save: function(data) {
        try {
            localStorage.setItem(this._key, JSON.stringify(data));
        } catch (e) {
            if (e.name === 'QuotaExceededError' || e.code === 22) {
                if (this._evictOldest(data)) {
                    this._save(data);
                } else {
                    alert('localStorage is full and no decks could be evicted.');
                }
            }
        }
    },

    /** Remove the least-recently-accessed deck from data (mutates). Returns true if one was removed. */
    _evictOldest: function(data) {
        var oldest = null;
        var oldestTime = Infinity;
        for (var name in data) {
            if (!data.hasOwnProperty(name)) continue;
            var t = data[name].last_accessed || 0;
            if (t < oldestTime) {
                oldestTime = t;
                oldest = name;
            }
        }
        if (oldest) {
            delete data[oldest];
            return true;
        }
        return false;
    },

    listDecks: function() {
        var data = this._load();
        var result = [];
        for (var name in data) {
            if (!data.hasOwnProperty(name)) continue;
            var deck = data[name];
            var cards = deck.cards || [];
            var commanders = [];
            var landCount = 0;
            for (var i = 0; i < cards.length; i++) {
                if (cards[i].commander) commanders.push(cards[i].name);
                if (cards[i].types && cards[i].types.indexOf('Land') !== -1) {
                    landCount += cards[i].quantity || 1;
                }
            }
            result.push({
                name: name,
                card_count: cards.length,
                commanders: commanders,
                land_count: landCount
            });
        }
        return result;
    },

    getDeck: function(name) {
        var data = this._load();
        if (!data[name]) return null;
        data[name].last_accessed = Date.now();
        this._save(data);
        return data[name];
    },

    saveDeck: function(name, cards, overrides) {
        var data = this._load();
        data[name] = {cards: cards, overrides: overrides || {}, last_accessed: Date.now()};
        this._save(data);
    },

    saveOverrides: function(name, overrides) {
        var data = this._load();
        if (data[name]) {
            data[name].overrides = overrides;
            data[name].last_accessed = Date.now();
            this._save(data);
        }
    },

    deleteDeck: function(name) {
        var data = this._load();
        delete data[name];
        this._save(data);
    },

    hasDeck: function(name) {
        var data = this._load();
        return name in data;
    }
};

/**
 * Navigate to the simulation page for a local deck.
 * POSTs deck data as JSON, replaces the page with the response.
 */
async function navigateToSim(deckName) {
    var deck = DeckStore.getDeck(deckName);
    if (!deck) { alert('Deck not found in local storage'); return; }
    var resp = await fetch('/sim/' + encodeURIComponent(deckName), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cards: deck.cards, overrides: deck.overrides})
    });
    if (!resp.ok) { alert('Failed to load simulation page'); return; }
    var html = await resp.text();
    document.open(); document.write(html); document.close();
    history.pushState(null, '', '/sim/' + encodeURIComponent(deckName));
}

/**
 * Navigate to the deck view page for a local deck.
 * POSTs deck data as JSON, replaces the page with the response.
 */
async function navigateToDeckView(deckName) {
    var deck = DeckStore.getDeck(deckName);
    if (!deck) { alert('Deck not found in local storage'); return; }
    var resp = await fetch('/decks/' + encodeURIComponent(deckName), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cards: deck.cards})
    });
    if (!resp.ok) { alert('Failed to load deck view'); return; }
    var html = await resp.text();
    document.open(); document.write(html); document.close();
    history.pushState(null, '', '/decks/' + encodeURIComponent(deckName));
}

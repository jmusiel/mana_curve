from mana_curve.decklist_model.goldfisher import main, get_parser

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    config.update(
        {
            "deck_name": "rabbits",
            "deck_url": "https://archidekt.com/decks/15875591/aristocratic_rabbits",
            "min_lands": 30,
            "max_lands": 40,
            "sims": 100000,
            "verbose": False,
        }
    )
    main(config=config)
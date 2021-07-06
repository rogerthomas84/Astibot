class CBProCurrencies:

    @staticmethod
    def get_all_pairs():
        return [
            "BTC-USD",
            "BTC-EUR",
            "ETH-USD",
            "ETH-EUR",
            "LTC-USD",
            "LTC-EUR",
            "BCH-USD",
            "BCH-EUR",
            "ETC-USD",
            "ETC-EUR",
            "BCH-BTC",
            "ETH-BTC",
            "LTC-BTC"
        ]

    @staticmethod
    def get_currencies_list():
        pairs = CBProCurrencies.get_all_pairs()
        currency_map = []
        for pair in pairs:
            pieces = pair.split('-')
            currency_map.append({
                "full": pair,
                "coin": pieces[0],
                "fiat": pieces[1]
            })

        return currency_map

    @staticmethod
    def get_index_for_currency_pair(pair):
        return CBProCurrencies.get_all_pairs().index(pair)

class CBProCurrencies:

    @staticmethod
    def get_all_pairs():
        return [
            "ADA-GBP",
            "BTC-GBP",
            "DOT-GBP",
            "CGLD-GBP",
            "ETH-GBP",
            "DOGE-GBP",
            "FORTH-GBP",
            "LTC-GBP",
            "NU-GBP"
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

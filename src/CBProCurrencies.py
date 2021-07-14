import json
import os
import pathlib

from Singleton import Singleton


@Singleton
class CBProCurrencies:

    _pairs = None  # type: list

    def __init__(self):
        print("Instance created")

    def get_all_pairs(self):
        if self._pairs is not None:
            return self._pairs

        json_pairs = self._load_pairs()

        if len(json_pairs) > 0:
            self._pairs = json_pairs
        else:
            self._pairs = [
                "ADA-GBP",
                "ANKR-GBP",
                "BTC-GBP",
                "DOT-GBP",
                "CGLD-GBP",
                "ETH-GBP",
                "DOGE-GBP",
                "FORTH-GBP",
                "LTC-GBP",
                "NU-GBP"
            ]

        return self._pairs

    def get_currencies_list(self):
        pairs = self.get_all_pairs()
        currency_map = []
        for pair in pairs:
            pieces = pair.split('-')
            currency_map.append({
                "full": pair,
                "coin": pieces[0],
                "fiat": pieces[1]
            })

        return currency_map

    def get_index_for_currency_pair(self, pair):
        return self.get_all_pairs().index(pair)

    def _load_pairs(self):
        """
        Loads the currencies.json file
        """
        tmp = pathlib.Path(__file__).parent.resolve().__str__()
        json_file_path = tmp + os.path.sep + "currencies.json"
        proposed = pathlib.Path(json_file_path)
        if proposed.exists() is False or proposed.is_file() is False:
            return []
        content = json.load(open(json_file_path))
        return content

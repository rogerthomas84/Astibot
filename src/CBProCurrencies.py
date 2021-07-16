import json
import os
import pathlib

import cbpro
from Singleton import Singleton


@Singleton
class CBProCurrencies:

    _pairs = None  # type: list
    _min_sizes = None  # type: dict

    def __init__(self):
        print("Instance created")

    def get_all_pairs(self):
        if self._pairs is not None:
            return self._pairs

        min_sizes = list(self.get_min_sizes().keys())
        min_sizes.sort()
        self._pairs = min_sizes
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

    def truncate_crypto_quantity_for_order(self, original, max_length):
        """
        Converts a figure into a non-rounded figure. Ex: (1.239, 0.01) would return 1.23 NOT 1.24.
        :rtype: float
        """
        tmp = max_length  # type: float
        the_string = "%.10f" % tmp
        the_string = the_string.strip("0").strip(".")
        number_cut = len(the_string)
        s = '{}'.format(original)
        if 'e' in s or 'E' in s:
            return '{0:.{1}f}'.format(original, number_cut)
        i, p, d = s.partition('.')
        return float('.'.join([i, (d + '0' * number_cut)[:number_cut]]).strip("0").strip("."))

    def get_min_size_for_pair(self, pair):
        """
        :rtype: float
        """
        min_sizes = self.get_min_sizes()  # type: dict
        if min_sizes is None:
            print("CBPro: get_min_sizes was None. Returning True")
            return None

        if pair not in min_sizes.keys():
            print("CBPro: pair was missing from min_sizes. Returning True")
            return None
        return min_sizes[pair]

    def get_min_sizes(self):
        if self._min_sizes is not None:
            return self._min_sizes
        print("CBProCurrencies: Fetching base increment sizes")
        products = cbpro.PublicClient().get_products()
        min_sizes = {}
        for p in products:  # type: dict
            if p.get("fx_stablecoin") is True:
                continue
            if p.get("status") != "online":
                continue
            if p.get("trading_disabled") is not False:
                continue
            min_sizes[p.get("id")] = float(p.get("base_increment"))
        self._min_sizes = min_sizes
        print("CBProCurrencies: Base increment sizes retrieved")
        return self._min_sizes

    def get_index_for_currency_pair(self, pair):
        return self.get_all_pairs().index(pair)

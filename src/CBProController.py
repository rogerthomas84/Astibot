import cbpro
from cbpro.public_client import PublicClient
import time
import threading
from json import dumps, loads
from cbpro.websocket_client import WebsocketClient
import TradingBotConfig as theConfig
from datetime import datetime
import pytz
from tzlocal import get_localzone
from requests.exceptions import ConnectionError
from CBProCurrencies import CBProCurrencies
import math # truncate


# This module is actually a Coinbae Pro handler
# TODO : update all CBPro references to CbPro
# noinspection PyPep8Naming,PyAttributeOutsideInit,SpellCheckingInspection,DuplicatedCode
class CBProController(cbpro.OrderBook):
    """
    classdocs
    """
    CBPRO_MAX_HISTORIC_PRICES_ELEMENTS = 300
    CBPRO_HISTORIC_DATA_MIN_GRANULARITY_IN_SEC = 60
    CBPRO_HISTORIC_DATA_SUBSCHEDULING_FACTOR = CBPRO_HISTORIC_DATA_MIN_GRANULARITY_IN_SEC / (theConfig.CONFIG_TIME_BETWEEN_RETRIEVED_SAMPLES_IN_MS / 1000)

    def __init__(self, UIGraph, Settings):

        first_currency = CBProCurrencies.instance().get_all_pairs()[0]
        super(CBProController, self).__init__(product_id=first_currency, log_to=False)

        self.theUIGraph = UIGraph
        # Application settings data instance
        self.theSettings = Settings

        self.webSocketIsOpened = False
        self.isRunning = True
        self.requestAccountsBalanceUpdate = True
        self.backgroundOperationsCounter = 0

        self.tickBestBidPrice = 0
        self.tickBestAskPrice = 0
        self.liveBestBidPrice = 0
        self.liveBestAskPrice = 0
        self.midMarketPrice = 0
        self.currentOrderId = 0
        self.currentOrderState = "NONE"  # SUBMITTED / OPENED / FILLED / NONE
        self.currentOrderInitialSizeInCrypto = 0
        self.currentOrderFilledSizeInCrypto = 0
        self.currentOrderAverageFilledPriceInFiat = 0

        self.productStr = self.theSettings.SETT_GetSettings()["strTradingPair"]
        self.productFiatStr = self.theSettings.SETT_GetSettings()["strFiatType"]
        self.productCryptoStr = self.theSettings.SETT_GetSettings()["strCryptoType"]
        self.bFiatAccountExists = False
        self.bCryptoAccountExists = False

        self.HistoricData = []
        self.HistoricDataReadIndex = 0
        self.HistoricDataSubSchedulingIndex = 0

        self.IsConnectedAndOperational = "False"

        self.clientPublic = cbpro.PublicClient()

        # Start background thread
        threadRefreshPrice = threading.Timer(1, self.updateRealTimePriceInBackground)
        threadRefreshPrice.start()

        # WebSocket thread
        # Websocket thread is launched by parent classes
        self.webSocketLock = threading.Lock()

        print("CBPro - CBPro Controler Initialization")

    def CBPro_IsConnectedAndOperational(self):
        return self.IsConnectedAndOperational

    # Fonction asynchrone
    def CBPro_InitializeCBProConnection(self):
        self.theUIGraph.UIGR_updateInfoText("Trying to connect...", False)
        self.IsConnectedAndOperational = "Requested"
        print("CBPro - Connection requested")

        if self.webSocketIsOpened is True:
            print("CBPro - Closing Websocket...")
            self.close()
            print("CBPro - Reseting Order book...")
            self.reset_book()
            # Orderbook class does not reset sequence number when changing product : set it to -1 will force orderbook to refresh
            # the sequence number and retrieve the last full order book
            self._sequence = -1

            self.liveBestBidPrice = 0
            self.liveBestAskPrice = 0

    def startWebSocketFeed(self):
        self.channels = ['full', 'user']
        self._log_to = False
        self.auth = True
        self.products = [self.productStr]
        self.start()

    def PerformConnectionInitializationAttempt(self):
        print("CBPro - Performing connection initialization attempt...")

        bCBProConnectionIsOK = True
        bInternetLinkIsOK = True
        self.bFiatAccountExists = False
        self.bCryptoAccountExists = False

        # Real Market keys =========================================
        self.api_key = self.theSettings.SETT_GetSettings()["strAPIKey"]
        self.api_secret = self.theSettings.SETT_GetSettings()["strSecretKey"]
        self.api_passphrase = self.theSettings.SETT_GetSettings()["strPassphrase"]

        # Use the sandbox API : https://api-public.sandbox.cbpro.com (requires a different set of API access credentials)
        # Use the true API : https://api.cbpro.com
        # noinspection PyUnusedLocal
        try:
            self.clientAuth = cbpro.AuthenticatedClient(self.api_key, self.api_secret, self.api_passphrase, api_url="https://api.pro.coinbase.com")
        except ConnectionError as e:
            print("CBPro - Internet connection error")
        except BaseException as e:
            bCBProConnectionIsOK = False
            bInternetLinkIsOK = False
            print("CBPro - Authentication error")
            print("CBPro - Exception : " + str(e))

        # Refresh account in order to see if auth was successful
        # noinspection PyUnusedLocal
        try:
            self.accounts = self.clientAuth.get_accounts()
            time.sleep(0.05)
            print("CBPro - Init, Accounts retrieved")
            if 'id' in self.accounts[0]:
                print("CBPro - Successful accounts retrieving")
            else:
                bCBProConnectionIsOK = False
                print("CBPro - Accounts retrieving not successful: no relevant data")
        except ConnectionError as e:
            print("CBPro - Internet connection error")
            bCBProConnectionIsOK = False
            bInternetLinkIsOK = False
        except BaseException as e:
            bCBProConnectionIsOK = False
            print("CBPro - Authentication error: not possible to get accounts data")
            print("CBPro - Exception : " + str(e))
            print("CBPro - clientAuth is: %s" % str(self.clientAuth))

        # If all steps before were successful, CBPro connection is working
        if bInternetLinkIsOK is True:
            if bCBProConnectionIsOK is True:
                # Check existence of right accounts
                for currentAccount in self.accounts:
                    if currentAccount['currency'] == self.productCryptoStr:
                        self.CryptoAccount = currentAccount
                        self.bCryptoAccountExists = True
                        print("CBPro - %s account has been found" % self.productCryptoStr)
                    if currentAccount['currency'] == self.productFiatStr:
                        self.FiatAccount = currentAccount
                        self.bFiatAccountExists = True
                        print("CBPro - %s account has been found" % self.productFiatStr)

                # If both accounts corresponding to the trading pair exist, init is successful
                if (self.bFiatAccountExists is True) and (self.bCryptoAccountExists is True):
                    print("CBPro - Initialization of CBPro connection successful")

                    # Start Websocket feed
                    self.startWebSocketFeed()

                    self.IsConnectedAndOperational = "True"
                    self.theUIGraph.UIGR_updateInfoText("Authentication successful", False)
                else:
                    print("CBPro - Accounts corresponding to the trading pairs do not exist")
                    self.IsConnectedAndOperational = "False"
                    # Display error message
                    if self.bFiatAccountExists is False:
                        self.theUIGraph.UIGR_updateInfoText("Error: No %s account found on your Coinbase Pro profile. Make sure you chose a trading pair that is available in your country" % self.productFiatStr, True)
                    else:
                        self.theUIGraph.UIGR_updateInfoText("Error: No %s account found on your Coinbase Pro profile. Make sure you chose a trading pair that you are authorized to trade" % self.productCryptoStr, True)

                self.refreshAccounts()
            else:
                print("CBPro - Initialization of CBPro connection failed")
                self.IsConnectedAndOperational = "False"
                # If first connection, display explanation message
                if self.theSettings.SETT_IsSettingsFilePresent() is False:
                    # Else, display error message
                    self.theUIGraph.UIGR_updateInfoText("Welcome on Astibot! Your Coinbase Pro API keys are required for trading. Click here to set it up", False)
                else:
                    # Else, display error message
                    self.theUIGraph.UIGR_updateInfoText("Coinbase Pro Authentication error: check your API credentials", True)
        else:
            print("CBPro - Initialization of CBPro connection failed")
            self.IsConnectedAndOperational = "False"
            # Display error message
            self.theUIGraph.UIGR_updateInfoText("Connection to Coinbase Pro server failed. Check your internet connection.", True)

    def CBPro_NotifyThatTradingPairHasChanged(self):
        self.productStr = self.theSettings.SETT_GetSettings()["strTradingPair"]
        self.productFiatStr = self.theSettings.SETT_GetSettings()["strFiatType"]
        self.productCryptoStr = self.theSettings.SETT_GetSettings()["strCryptoType"]
        self.HistoricData = []
        self.HistoricDataReadIndex = 0

    # Returns the Available fiat balance (ie. money that can be used and that is not held for any pending order)
    def CBPro_GetFiatAccountBalance(self):
        # print("CBPro - GetFiatAccountBalance")
        if self.bFiatAccountExists is True:
            # print("CBPro - Exists")
            # noinspection PyBroadException,PyUnusedLocal
            try:
                balanceToReturn = (round(float(self.FiatAccount['available']), 8))
                return balanceToReturn
            except BaseException as e:
                print("CBPro - Error retrieving fiat account balance. Inconsistent data in fiat account object.")
                return 0
        else:
            print("CBPro - Does not exist")
            return 0

    def CBPro_GetFiatAccountBalanceHeld(self):
        # print("CBPro - GetFiatAccountBalance")
        if self.bFiatAccountExists is True:
            # print("CBPro - Exists")
            # noinspection PyBroadException,PyUnusedLocal
            try:
                balanceToReturn = (round(float(self.FiatAccount['hold']), 8))
                return balanceToReturn
            except BaseException as e:
                print("CBPro - Error retrieving fiat hold account balance. Inconsistent data in fiat account object.")
                return 0
        else:
            print("CBPro - Does not exist")
            return 0

    # Returns the Available crypto balance (ie. money that can be used and that is not held for any pending order)
    def CBPro_GetCryptoAccountBalance(self):
        if self.bCryptoAccountExists is True:
            # noinspection PyBroadException,PyUnusedLocal
            try:
                balanceToReturn = (round(float(self.CryptoAccount['available']), 8))
                return balanceToReturn
            except BaseException as e:
                print("CBPro - Error retrieving crypto account balance. Inconsistent data in crypto account object.")
                return 0
        else:
            print("CBPro - Error retrieving crypto account balance. Crypto account does not exist")
            return 0

    def CBPro_GetCryptoAccountBalanceHeld(self):
        if self.bCryptoAccountExists is True:
            # noinspection PyBroadException,PyUnusedLocal
            try:
                balanceToReturn = (round(float(self.CryptoAccount['hold']), 8))
                print("CBPro - Returned held balance %s for %s" % (balanceToReturn, self.productCryptoStr))
                return balanceToReturn
            except BaseException as e:
                print("CBPro - Error retrieving crypto hold account balance. Inconsistent data in crypto account object.")
                return 0
        else:
            print("CBPro - Error retrieving crypto account balance. Crypto account does not exist")
            return 0

    # Returns the Available BTC balance (ie. money that can be used and that is not held for any pending order)
    # Useful for payment system
    def CBPro_GetBTCAccountBalance(self):
        # noinspection PyUnusedLocal,PyBroadException
        try:
            for currentAccount in self.accounts:
                if currentAccount['currency'] == 'BTC':
                    balanceToReturn = round(float(currentAccount['available']), 7)
                    return balanceToReturn
            return 0
        except BaseException as e:
            print("CBPro - Error retrieving crypto account balance. Inconsistent data in crypto account object.")
            return 0

    def refreshAccounts(self):
        # noinspection PyBroadException,PyUnusedLocal
        try:
            self.accounts = self.clientAuth.get_accounts()
            # Refresh individual accounts
            for currentAccount in self.accounts:
                if currentAccount['currency'] == self.productCryptoStr:
                    self.CryptoAccount = currentAccount
                    # print("CRYPTO ACCOUNT")
                    # print(self.CryptoAccount)
                    # print(self.CryptoAccount['balance'])
                    # print(self.CryptoAccount['available'])
                if currentAccount['currency'] == self.productFiatStr:
                    self.FiatAccount = currentAccount
                    # print("FIAT ACCOUNT")
                    # print(self.FiatAccount)
                    # print(self.FiatAccount['balance'])
                    # print(self.FiatAccount['available'])

            if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:
                self.theUIGraph.UIGR_updateAccountsBalance(self.CBPro_GetFiatAccountBalance(), self.CBPro_GetCryptoAccountBalance())
            else:
                pass  # In simulated market, accounts are refreshed by the Simulation manager
        except Exception as e:
            print("CBPro - Error in refreshAccounts")

    def CBPro_RefreshAccountsDisplayOnly(self):
        if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:
            self.theUIGraph.UIGR_updateAccountsBalance(self.CBPro_GetFiatAccountBalance(), self.CBPro_GetCryptoAccountBalance())
        else:
            pass  # TRNM takes care of the price update

    # WebSocket callback - On connection opening
    def on_open(self):
        print("CBPro - WebSocket connection opened (callback) on %s" % self.productStr)
        # self.url = "wss://ws-feed.pro.coinbase.com/"
        self.products = [self.productStr]
        self.webSocketIsOpened = True
        self.count = 0
        self.matchOrderProcessedSequenceId = 0

    def on_message(self, message):
        super(CBProController, self).on_message(message)

        self.webSocketLock.acquire()

        # Listen for user orders
        if 'order_id' in message:
            if message['order_id'] == self.currentOrderId:
                print("CBPro - Current order msg: %s" % message)
                order_type = message['type']
                if order_type == 'open':
                    self.currentOrderState = "OPENED"
                    print("CBPro - on_message: current order state updated to OPENED")
                elif order_type == 'done':
                    if message['reason'] == 'canceled':
                        self.currentOrderId = 0
                        self.currentOrderState = "NONE"
                        self.currentOrderInitialSizeInCrypto = 0
                        self.currentOrderFilledSizeInCrypto = 0
                        self.currentOrderAverageFilledPriceInFiat = 0
                        print("CBPro - on_message: current order canceled")
                    elif float(message['remaining_size']) < theConfig.CONFIG_CRYPTO_PRICE_QUANTUM:
                        self.currentOrderState = "FILLED"
                        print("CBPro - on_message: current order totally filled (to check). Refresh accounts now")
                        self.refreshAccounts()

        # Match messages do not have an "order_id" field but a maker/taker_order_id field
        if 'maker_order_id' in message:
            if message['maker_order_id'] == self.currentOrderId:
                print("CBPro - Current order msg: %s" % message)
                if (message['type'] == 'match') and ('size' in message):
                    # To preserve buy price calculation integrity, matched order must be processed once (but it appears both in user and full channels)
                    # If this matched message is not processed yet
                    if self.matchOrderProcessedSequenceId != message['sequence']:
                        print("CBPro - on_message: current order has been matched")
                        newFillAverageInFiat = (self.currentOrderAverageFilledPriceInFiat*self.currentOrderFilledSizeInCrypto + float(message['size']) * float(message['price'])) / (self.currentOrderFilledSizeInCrypto + float(message['size']))
                        self.currentOrderFilledSizeInCrypto += float(message['size'])
                        print("CBPro - on_message: average order fill price updated from %s to %s" % (self.currentOrderAverageFilledPriceInFiat, newFillAverageInFiat))
                        print("CBPro - on_message: current order total fill quantity updated to %s" % self.currentOrderFilledSizeInCrypto)
                        self.currentOrderAverageFilledPriceInFiat = newFillAverageInFiat
                        self.matchOrderProcessedSequenceId = message['sequence']
                        self.currentOrderState = "MATCHED"

        # Order book has been updated, retrieve best bid and ask
        self.liveBestBidPrice = self.get_bid()
        # print("Bid %s" % self.liveBestBidPrice)
        self.liveBestAskPrice = self.get_ask()
        # print("Ask %s" % self.liveBestAskPrice)

        self.webSocketLock.release()

    def on_close(self):
        print("CBPro - WebSocket connection closed (callback)")
        self.webSocketIsOpened = False

        if self.isRunning:  # If we are not exiting app
            if self.IsConnectedAndOperational != "Requested" and self.IsConnectedAndOperational != "Ongoing":  # If we are not re-initializing connection (like settings apply)
                print("CBPro - Unexpected close of websocket. Trying to restart.")
                while self.isRunning is True and self.webSocketIsOpened is False:
                    print("CBPro - Restarting Websocket in 10 seconds...")
                    time.sleep(10)
                    self.startWebSocketFeed()
        print("CBPro - End of on_close()")

    def CBPro_GetLiveBestBidPrice(self):
        self.webSocketLock.acquire()
        liveBestBidPriceToReturn = self.liveBestBidPrice
        self.webSocketLock.release()

        return liveBestBidPriceToReturn

    def CBPro_GetLiveBestAskPrice(self):
        self.webSocketLock.acquire()
        liveBestAskPriceToReturn = self.liveBestAskPrice
        self.webSocketLock.release()

        return liveBestAskPriceToReturn

    def updateRealTimePriceInBackground(self):

        while self.isRunning is True:

            # Attempt a CBPro Initialization if requested
            if self.IsConnectedAndOperational == "Requested":
                self.IsConnectedAndOperational = "Ongoing"
                self.PerformConnectionInitializationAttempt()
                time.sleep(1)  # Don't poll CBPro API too much

            self.backgroundOperationsCounter = self.backgroundOperationsCounter + 1

            # Get Middle Market Price ==========================================================
            # Order book level 1 : Just the highest bid and lowest sell proposal
            try:
                result = ""
                result = self.clientPublic.get_product_order_book(self.productStr, 1)
                self.tickBestBidPrice = float(result['bids'][0][0])
                self.tickBestAskPrice = float(result['asks'][0][0])
                self.midMarketPrice = (self.tickBestBidPrice + self.tickBestAskPrice) / 2

                # DEBUG
#                 print("CBPro - Highest Bid: %s" % self.tickBestBidPrice)
#                 print("CBPro - Lowest Ask: %s" % self.tickBestAskPrice)

                self.PriceSpread = self.tickBestBidPrice - self.tickBestAskPrice
                # print("CBPro - MiddleMarket price: %s" % self.tickBestBidPrice)

                self.theUIGraph.UIGR_updateConnectionText("Price data received from Coinbase Pro server")

                # Refresh account balances
                # Only do it if CBPro controler is OK in authenticated mode
                if self.IsConnectedAndOperational == "True":
                    if (self.backgroundOperationsCounter % 20 == 0) or (self.requestAccountsBalanceUpdate is True):
                        self.requestAccountsBalanceUpdate = False
                        if self.IsConnectedAndOperational == "True":
                            self.refreshAccounts()

            except BaseException as e:
                print("CBPro - Error retrieving level 1 order book or account data")
                print("CBPro - Exception : " + str(e))
                # noinspection PyUnboundLocalVariable
                print(result)
                self.requestAccountsBalanceUpdate = False

            # Get current Orders ===============================================================

            for x in range(0, 5):
                if self.requestAccountsBalanceUpdate is False:
                    time.sleep(0.1)

            self.theUIGraph.UIGR_resetConnectionText()

            for x in range(0, 15):
                if self.requestAccountsBalanceUpdate is False:
                    time.sleep(0.1)

    def CBPro_closeBackgroundOperations(self):

        self.isRunning = False

        if self.webSocketIsOpened is True:
            print("CBPro - Closing Websocket...")
            self.close()

    def CBPro_GetRealTimePriceInEUR(self):
        return self.midMarketPrice

    def CBPro_GetCurrentLimitOrderState(self):
        self.webSocketLock.acquire()
        currentState = self.currentOrderState

        if currentState == "FILLED":
            self.currentOrderState = "NONE"

        self.webSocketLock.release()

        return currentState

    def CBPro_GetAveragePriceInFiatAndSizeFilledInCrypto(self):
        print("CBPro - CBPro_GetAveragePriceInFiatAndSizeFilledInCrypto : AverageFilledPrice = %s, currentOrderFilledSizeInCrypo = %s" % (self.currentOrderAverageFilledPriceInFiat, self.currentOrderFilledSizeInCrypto))
        return [self.currentOrderAverageFilledPriceInFiat, self.currentOrderFilledSizeInCrypto]

    def CBPro_PlaceLimitBuyOrder(self, amountToBuyInCrypto, buyPriceInFiat):

        self.webSocketLock.acquire()

        if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:

            print("CBPro - CBPro_PlaceLimitBuyOrder")

            # First, cancel ongoing order if any
            if self.currentOrderState != "NONE":
                self.INTERNAL_CancelOngoingLimitOrder()

            # Send Limit order
            amountToBuyInCrypto = round(amountToBuyInCrypto, 8)

            # Don't use round because order could be placed on the other side of the spread -> rejected
            # Prix exprimé en BTC, arrondi variable
            if self.productFiatStr == "BTC":
                if self.productCryptoStr == "LTC":
                    buyPriceInFiat = math.floor(buyPriceInFiat*1000000)/1000000  # Floor à 0.000001
                else:
                    buyPriceInFiat = math.floor(buyPriceInFiat*100000)/100000  # Floor à 0.00001
            else:  # Prix exprimé en Fiat, arrondi à 0.01
                buyPriceInFiat = math.floor(buyPriceInFiat*100)/100

            buyRequestReturn = self.clientAuth.buy(price=str(buyPriceInFiat), size=str(amountToBuyInCrypto), product_id=self.productStr, order_type='limit', post_only=True)  # with Post Only
            print("CBPro - Actual buy sent with LIMIT order set to %s. Amount is %s Crypto" % (buyPriceInFiat, amountToBuyInCrypto))
            print("CBPro - Limit order placing sent. Request return is: %s" % buyRequestReturn)
            if 'id' in buyRequestReturn:
                if 'reject_reason' not in buyRequestReturn:
                    self.currentOrderId = buyRequestReturn['id']
                    self.currentOrderState = "SUBMITTED"
                    self.currentOrderInitialSizeInCrypto = amountToBuyInCrypto
                    self.currentOrderFilledSizeInCrypto = 0
                    self.currentOrderAverageFilledPriceInFiat = 0
                    print("CBPro - Limit order state set to SUBMITTED")

                    self.webSocketLock.release()
                    return True
                else:
                    print("CBPro - Buy limit order has been interpreted as rejected. Reason: %s" % buyRequestReturn['reject_reason'])

                    self.webSocketLock.release()
                    return False
            else:
                print("CBPro - Buy limit order has been interpreted as rejected")

                self.webSocketLock.release()
                return False
        else:
            # Simulation mode: simulate immediate order fill
            self.currentOrderId = -1
            self.currentOrderFilledSizeInCrypto = float(amountToBuyInCrypto)
            self.currentOrderAverageFilledPriceInFiat = float(buyPriceInFiat)
            print("CBPro - Limit buy simulated, buy price: %s, amountToBuyInCrypto: %s" % (round(float(buyPriceInFiat), 2), float(amountToBuyInCrypto)))
            self.currentOrderState = "FILLED"

            self.webSocketLock.release()
            return True

    def CBPro_PlaceLimitSellOrder(self, amountToSellInCrypto, sellPriceInFiat):

        if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:

            self.webSocketLock.acquire()

            # First, cancel ongoing order if any
            if self.currentOrderState != "NONE":
                self.INTERNAL_CancelOngoingLimitOrder()

            # Send Limit order
            amountToSellInCrypto = round(amountToSellInCrypto, 8)

            # Don't use round because order could be placed on the other side of the spread -> rejected
            # Prix exprimé en BTC, arrondi variable
            if self.productFiatStr == "BTC":
                if self.productCryptoStr == "LTC":
                    sellPriceInFiat = math.floor(sellPriceInFiat*1000000)/1000000  # Floor à 0.000001
                else:
                    sellPriceInFiat = math.floor(sellPriceInFiat*100000)/100000  # Floor à 0.00001
            else:  # Prix exprimé en Fiat, arrondi à 0.01
                sellPriceInFiat = math.floor(sellPriceInFiat*100)/100

            sellRequestReturn = self.clientAuth.sell(price=str(sellPriceInFiat), size=str(amountToSellInCrypto), product_id=self.productStr, order_type='limit', post_only=True)  # with Post Only
            print("CBPro - Actual sell sent with LIMIT order set to %s. Amount is %s Crypto" % (sellPriceInFiat, amountToSellInCrypto))
            print("CBPro - Limit order placing sent. Request return is: %s" % sellRequestReturn)
            if 'id' in sellRequestReturn:
                self.currentOrderId = sellRequestReturn['id']
                self.currentOrderState = "SUBMITTED"
                self.currentOrderInitialSizeInCrypto = amountToSellInCrypto
                self.currentOrderFilledSizeInCrypto = 0
                self.currentOrderAverageFilledPriceInFiat = 0

                self.webSocketLock.release()
                return True
            else:
                print("CBPro - Sell limit order has been interpreted as rejected")

                self.webSocketLock.release()
                return False
        else:
            # Simulation mode: simulate immediate order fill
            self.currentOrderFilledSizeInCrypto = amountToSellInCrypto
            self.currentOrderAverageFilledPriceInFiat = sellPriceInFiat
            self.currentOrderState = "FILLED"

            self.webSocketLock.release()
            return True

    # Include thread safe protection: shall be called from outside
    def CBPro_CancelOngoingLimitOrder(self):
        self.webSocketLock.acquire()
        if self.currentOrderId != 0:
            self.currentOrderId = 0  # So that websocket won't get the cancel notification
            self.currentOrderState = "NONE"
            self.currentOrderInitialSizeInCrypto = 0
            self.currentOrderFilledSizeInCrypto = 0
            self.currentOrderAverageFilledPriceInFiat = 0
            cancelAllReturn = self.clientAuth.cancel_all(self.productStr)
            print("CBPro - CBPro_CancelOngoingLimitOrder: Ongoing order canceled. Request return is: %s" % cancelAllReturn)
        else:
            print("CBPro - CBPro_CancelOngoingLimitOrder: No order to cancel! Just filled?")
        self.webSocketLock.release()

    # Does not include thread safe protection: shall not be called from outside
    def INTERNAL_CancelOngoingLimitOrder(self):

        if self.currentOrderId != 0:
            self.currentOrderId = 0  # So that websocket won't get the cancel notification
            self.currentOrderState = "NONE"
            self.currentOrderInitialSizeInCrypto = 0
            self.currentOrderFilledSizeInCrypto = 0
            self.currentOrderAverageFilledPriceInFiat = 0
            cancelAllReturn = self.clientAuth.cancel_all(self.productStr)
            print("CBPro - INTERNAL_CancelOngoingLimitOrder: Ongoing order canceled. Request return is: %s" % cancelAllReturn)
        else:
            print("CBPro - INTERNAL_CancelOngoingLimitOrder: No order to cancel! Just filled?")

    def CBPro_SendBuyOrder(self, amountToBuyInBTC):
        if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:
            if theConfig.CONFIG_ENABLE_REAL_TRANSACTIONS is True:
                # Prepare the right amount to buy precision. Smallest CBPro unit is 0.00000001
                amountToBuyInBTC = round(amountToBuyInBTC, 8)

                # Send Market order
                buyRequestReturn = self.clientAuth.buy(size=amountToBuyInBTC, product_id=self.productStr, order_type='market')
                print("CBPro - Actual buy sent with MARKET order. Amount is %s BTC" % amountToBuyInBTC)

                print("CBPro - Buy Request return is : \n %s \nCBPro - End of Request Return" % buyRequestReturn)

                self.requestAccountsBalanceUpdate = True

                # Check if order was successful or not depending on existence of an order ID in the request response
                if 'id' in buyRequestReturn:
                    print("CBPro - Buy order has been interpreted as successful")
                    return True
                else:
                    print("CBPro - Buy order has been interpreted as failed")
                    return False
        return False

    def CBPro_SendSellOrder(self, amountToSellInBTC):
        if theConfig.CONFIG_INPUT_MODE_IS_REAL_MARKET is True:
            if theConfig.CONFIG_ENABLE_REAL_TRANSACTIONS is True:
                # Prepare the right amount to sell precision. Smallest CBPro unit is 0.00000001
                amountToSellInBTC = round(amountToSellInBTC, 8)

                # Send Market order
                sellRequestReturn = self.clientAuth.sell(size=amountToSellInBTC, product_id=self.productStr, order_type='market')
                print("Actual sell sent with MARKET order. Amount is %s" % amountToSellInBTC)

                print("CBPro - Sell Request return is : \n %s \nCBPro - End of Request Return" % sellRequestReturn)
                time.sleep(0.1)
                self.refreshAccounts()
                time.sleep(0.1)
                self.requestAccountsBalanceUpdate = True

                # Check if order was successful or not depending on existence of an order ID in the request response
                if 'id' in sellRequestReturn:
                    print("CBPro - Sell order has been interpreted as successful")
                    return True
                else:
                    print("CBPro - Sell order has been interpreted as failed")
                    return False
            else:
                return False
        else:
            return False

    def CBPro_IsAmountToBuyAboveMinimum(self, amountOfCryptoToBuy):
        if self.theSettings.SETT_GetSettings()["strCryptoType"] == "BTC":
            if amountOfCryptoToBuy > 0.001:
                return True
            else:
                return False

        if self.theSettings.SETT_GetSettings()["strCryptoType"] == "BCH":
            if amountOfCryptoToBuy > 0.01:
                return True
            else:
                return False

        if self.theSettings.SETT_GetSettings()["strCryptoType"] == "LTC":
            if amountOfCryptoToBuy > 0.1:
                return True
            else:
                return False

        if self.theSettings.SETT_GetSettings()["strCryptoType"] == "ETH":
            if amountOfCryptoToBuy > 0.01:
                return True
            else:
                return False

        if self.theSettings.SETT_GetSettings()["strCryptoType"] == "ETC":
            if amountOfCryptoToBuy > 0.1:
                return True
            else:
                return False

        return True

    def CBPro_WithdrawBTC(self, destinationAddress, amountToWithdrawInBTC):
        print("CBPro - Withdraw BTC")

        if theConfig.CONFIG_DEBUG_ENABLE_DUMMY_WITHDRAWALS is False:
            withdrawRequestReturn = self.clientAuth.crypto_withdraw(amountToWithdrawInBTC, 'BTC', destinationAddress)

            print("CBPro - Withdraw request return: %s" % withdrawRequestReturn)
            # Check if withdraw was successful or not depending on existence of an order ID in the request response
            if 'id' in withdrawRequestReturn:
                print("CBPro - Withdraw has been interpreted as successful")
                return withdrawRequestReturn['id']
            else:
                print("CBPro - Withdraw has failed")
                return "Error"
        else:
            return "Dummy Withdraw"

    def CBPro_RequestAccountsBalancesUpdate(self):
        self.requestAccountsBalanceUpdate = True

    def CBPro_LoadHistoricData(self, startTimestamp, stopTimestamp):

        print("Init to retrieve Historic Data from %s to %s" % (datetime.fromtimestamp(startTimestamp).isoformat(), datetime.fromtimestamp(stopTimestamp).isoformat()))
        print("---------")
        # Reset read index are we will overwrite the buffer
        self.HistoricDataReadIndex = 0

        local_tz = get_localzone()
        print("CBPro - Local timezone found: %s" % local_tz)
        tz = pytz.timezone(str(local_tz))

        stopSlice = 0
        startSlice = startTimestamp
        self.HistoricDataRaw = []
        self.HistoricData = []

        # Progression measurement
        granularityInSec = round(self.CBPRO_HISTORIC_DATA_MIN_GRANULARITY_IN_SEC)
        nbIterationsToRetrieveEverything = ((stopTimestamp - startTimestamp) / (round(self.CBPRO_HISTORIC_DATA_MIN_GRANULARITY_IN_SEC))) / round(self.CBPRO_MAX_HISTORIC_PRICES_ELEMENTS)
        print("CBPro - Nb Max iterations to retrieve everything: %s" % nbIterationsToRetrieveEverything)
        nbLoopIterations = 0

        while stopSlice < stopTimestamp:

            stopSlice = startSlice + self.CBPRO_MAX_HISTORIC_PRICES_ELEMENTS * granularityInSec
            if stopSlice > stopTimestamp:
                stopSlice = stopTimestamp
            print("CBPro - Start TS : %s  stop TS : %s" % (startSlice, stopSlice))

            startTimestampSliceInISO = datetime.fromtimestamp(startSlice, tz).isoformat()
            stopTimestampSliceInISO = datetime.fromtimestamp(stopSlice, tz).isoformat()
            print("CBPro - Retrieving Historic Data from %s to %s" % (startTimestampSliceInISO, stopTimestampSliceInISO))
            if self.IsConnectedAndOperational == "True":
                print("CBPro - Using public client to retrieve historic prices")
                HistoricDataSlice = self.clientAuth.get_product_historic_rates(self.productStr, granularity=granularityInSec, start=startTimestampSliceInISO, end=stopTimestampSliceInISO)
                # Only sleep if re-loop condition is met
                if stopSlice < stopTimestamp:
                    time.sleep(0.350)
                print("CBPro - Using private client to retrieve historic prices")
            else:
                HistoricDataSlice = self.clientPublic.get_product_historic_rates(self.productStr, granularity=granularityInSec, start=startTimestampSliceInISO, end=stopTimestampSliceInISO)
                # Only sleep if re-loop condition is met
                if stopSlice < stopTimestamp:
                    time.sleep(0.250)
                print("CBPro - Using public client to retrieve historic prices")

            print("CBPro - Size of HistoricDataSlice: %s" % len(HistoricDataSlice))

            # noinspection PyBroadException,SpellCheckingInspection,PyUnusedLocal
            try:  # parfois le reversed crash. Pas de data dans la slice ?
                for piece in reversed(HistoricDataSlice):
                    self.HistoricDataRaw.append(piece)
            except BaseException as e:
                print("CBPro - Exception when reversing historic data slice")
            # print("Historic : %s " % HistoricDataSlice)

            startSlice = stopSlice  # Prepare next iteration

            # Progress report
            nbLoopIterations = nbLoopIterations + 1
            percentage = round(nbLoopIterations * 100 / nbIterationsToRetrieveEverything)
            if percentage > 100:
                percentage = 100
            self.theUIGraph.UIGR_updateLoadingDataProgress(str(percentage))

        # Clean buffer so that only data in the chronological order remains
        print("CBPro - LoadHistoricData - Cleaning buffer. Nb elements before cleaning : %s" % len(self.HistoricDataRaw))
        tempIterationIndex = 0
        currentBrowsedTimestamp = 0
        while tempIterationIndex < len(self.HistoricDataRaw):
            if self.HistoricDataRaw[tempIterationIndex][0] <= currentBrowsedTimestamp + 1:
                # Useless data : do not copy into final buffer
                pass
            else:
                currentBrowsedTimestamp = self.HistoricDataRaw[tempIterationIndex][0]
                self.HistoricData.append(self.HistoricDataRaw[tempIterationIndex])

            # print(self.HistoricData[tempIterationIndex][0])
            tempIterationIndex = tempIterationIndex + 1

# DEBUG
#         tempIterationIndex = 0
#         while (tempIterationIndex < len(self.HistoricData)):
#             print(self.HistoricData[tempIterationIndex][0])
#             tempIterationIndex = tempIterationIndex + 1
#
        print("CBPro - %s Historical samples have been retrieved (after cleaning)" % len(self.HistoricData))

    # Returns a price data sample CONFIG_TIME_BETWEEN_RETRIEVED_SAMPLES_IN_MS seconds after the last call
    # even if CBPro historic sample period is longer
    def CBPro_GetNextHistoricDataSample(self):
        # print("HistoricData : %s " % self.HistoricData)
        # print("CBPro - Full Historic data list length is %s" % len(self.HistoricData))

        endOfList = False
        self.HistoricDataReadIndex = self.HistoricDataReadIndex + 1
        if self.HistoricDataReadIndex + 1 >= len(self.HistoricData):  # We've read as many samples as they are in the list
            endOfList = True
            print("CBPro - Historic Data - End of list reached")
#         print("Time retrieved %s" % self.HistoricData[self.HistoricDataReadIndex][0])
#         print("Price retrieved %s" % self.HistoricData[self.HistoricDataReadIndex][4])
#         print("Len list %s, Index : %s" % (len(self.HistoricData), self.HistoricDataReadIndex))

        # Fifth element (index 4) is the closure price
        return [self.HistoricData[self.HistoricDataReadIndex][0], self.HistoricData[self.HistoricDataReadIndex][4], endOfList]

    def CBPro_SetReadIndexFromPos(self, positionTimeStamp):
        tempIterationIndex = 0
        bReadIndexFound = False
        print("CBPro - SetReadIndexFromPos : %d" % positionTimeStamp)
        print("CBPro - Historic data length is %s" % len(self.HistoricData))

        while (tempIterationIndex < len(self.HistoricData)) and (bReadIndexFound is False):
            if self.HistoricData[tempIterationIndex][0] > positionTimeStamp:
                self.HistoricDataReadIndex = tempIterationIndex
                bReadIndexFound = True
            tempIterationIndex = tempIterationIndex + 1

        if bReadIndexFound is True:
            print("CBPro - SetReadIndexFromPos : index found: %s" % self.HistoricDataReadIndex)
            return True
        else:
            print("CBPro - SetReadIndexFromPos : index not found")
            return False

    # Return the number of samples that can be read starting from the current readIndex position, until the end of the buffer
    def CBPro_GetNumberOfSamplesLeftToRead(self):
        nbOfSamplesLeftToRead = len(self.HistoricData) - self.HistoricDataReadIndex
        print("CBPro - Number of samples left to read is %s" % nbOfSamplesLeftToRead)
        return nbOfSamplesLeftToRead

    def CBPro_GetHistoricDataSubSchedulingFactor(self):
        return self.CBPRO_HISTORIC_DATA_SUBSCHEDULING_FACTOR

    def CBPro_GetLoadedDataStartTimeStamp(self):
        if len(self.HistoricData) > 2:
            return self.HistoricData[0][0]
        else:
            return 99999999999

    def CBPro_GetLoadedDataStopTimeStamp(self):
        if len(self.HistoricData) > 2:
            return self.HistoricData[-1][0]
        else:
            return 0

    def CBPro_ListAccountWithdrawals(self):
        print(self.clientAuth.get_account_history(self.CryptoAccount['id']))

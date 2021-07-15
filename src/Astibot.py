#!.

import fix_path
# noinspection PyUnresolvedReferences
import threading
# noinspection PyUnresolvedReferences
import time
# noinspection PyUnresolvedReferences
import sys
# noinspection PyUnresolvedReferences
import ipdb  # To be able to see error stack messages occurring in the Qt MainLoop
import os

from Settings import Settings
from MarketData import MarketData
from InputDataHandler import InputDataHandler
from CBProController import CBProController
from TransactionManager import TransactionManager
from Trader import Trader
from UIGraph import UIGraph
from AppState import AppState
# noinspection PyUnresolvedReferences
import TradingBotConfig as theConfig
import pyqtgraph as pg
from CBProCurrencies import CBProCurrencies

from pyqtgraph.Qt import QtCore, QtGui  # Only useful for splash screen


CBProCurrencies.instance()


# noinspection PyUnresolvedReferences,PyPep8Naming
class TradingBot(object):

    def __init__(self):
        cwd = os.getcwd()
        print("Running Astibot in: %s" % cwd)

        self.isInitializing = True
        self.iterationCounter = 0
        self.historicPriceIterationCounter = 0
        self.theSettings = Settings()

        self.app = pg.QtGui.QApplication(['Astibot'])

        # Show Splash Screen
        splash_pix = QtGui.QPixmap(self.theSettings.SETT_get_resource_path_for_file('AstibotSplash.png'))
        splash = QtGui.QSplashScreen(splash_pix, QtCore.Qt.WindowStaysOnTopHint)
        splash.show()

        # Instantiate objects
        self.theUIGraph = UIGraph(self.app, self.theSettings)
        self.theCBProController = CBProController(self.theUIGraph, self.theSettings)
        self.theMarketData = MarketData(self.theCBProController, self.theUIGraph)
        self.theTransactionManager = TransactionManager(self.theCBProController, self.theUIGraph, self.theMarketData, self.theSettings)
        self.theUIGraph.UIGR_SetTransactionManager(self.theTransactionManager)
        self.theTrader = Trader(self.theTransactionManager, self.theMarketData, self.theUIGraph, self.theSettings)
        self.theInputDataHandler = InputDataHandler(self.theCBProController, self.theUIGraph, self.theMarketData, self.theTrader, self.theSettings)
        self.theApp = AppState(self.theUIGraph, self.theTrader, self.theCBProController, self.theInputDataHandler, self.theMarketData, self.theSettings)

        # Setup Main Tick Timer
        self.mainTimer = pg.QtCore.QTimer()
        self.mainTimer.timeout.connect(self.MainTimerHandler)
        self.mainTimer.start(100)

        # Hide splash screen
        splash.close()

        # Endless call
        self.app.exec_()

        # App closing
        self.theCBProController.CBPro_closeBackgroundOperations()
        self.theInputDataHandler.INDH_closeBackgroundOperations()
        self.theUIGraph.UIGR_closeBackgroundOperations()

    def MainTimerHandler(self):
        self.theApp.APP_Execute()


if __name__ == '__main__':
    theTradingBot = TradingBot()

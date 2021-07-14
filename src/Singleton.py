class Singleton:

    def __init__(self, decorated):
        self._decorated = decorated

    def instance(self):
        """
        Get instance of this singleton
        """
        try:
            return self._instance
        except AttributeError:
            self._instance = self._decorated()
            return self._instance

    def __call__(self):
        raise TypeError('Call with instance method')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)

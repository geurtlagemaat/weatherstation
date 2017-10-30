__author__ = 'geurt'

from twisted.protocols.basic import LineReceiver
import traceback

class SerialBusReceiver(LineReceiver):

    def __init__(self, NodeControl, OnReceive):
        self._NodeControl = NodeControl
        self._OnReceive = OnReceive

    def lineReceived(self, line):
        self._NodeControl.log.debug("line: %s." % (line))
        if len(line) > 0 and ';' in line:
            try:
                self._OnReceive(line)
            except Exception, exp:
                self._NodeControl.log.info(
                    "Error reading serial line: [%s], error: %s." % (traceback.format_exc(), line))
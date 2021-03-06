from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.serialport import SerialPort, serial
import datetime, traceback
from SerialBusReceiver import SerialBusReceiver

class SerialBusMaster(object):
    def __init__(self, oNodeControl):
        self._NodeControl = oNodeControl
        self._windData = []
        self._isRainInit = True

        myProtocol = SerialBusReceiver(oNodeControl, OnReceive=self.OnMsgReceive)

        SerialPort(myProtocol, oNodeControl.nodeProps.get('serial', 'port'),
                   reactor,
                   baudrate=oNodeControl.nodeProps.get('serial', 'baudrate'),
                   bytesize=serial.EIGHTBITS,
                   parity=serial.PARITY_NONE)

        l = task.LoopingCall(self.eUpdateWind)
        l.start(60)

    def eUpdateWind(self):
        if self._windData is not None and len(self._windData):
            try:
                minuteWindMPH = sum(self._windData)/len(self._windData)
                minuteWindKMH = minuteWindMPH * 1.60934
                minuteWindMtrSec = minuteWindKMH / 3.6
                minuteFormatedValue = '{:.1f}'.format(minuteWindMtrSec)
                self._NodeControl.setProperty('curr-windspeed', minuteFormatedValue)
                del self._windData[:]
            except Exception, exp:
                self._NodeControl.log.warning("Error calculation average wind data, error: %s." % (traceback.format_exc()))

    def OnMsgReceive(self, RecMsg):
        """
        event that is triggerd when a serial message is received. Send ack and publish when needed to MQTT
        """

        """
        Serial.print("WIND_SPEED:MPH:");
        Serial.print(windSpeedMPH);
        Serial.println(";");
        en
        RAIN_DETECT;
        """
        if "WIND_SPEED:MPH:" in RecMsg:
            MyWindSpeedMPH = RecMsg[RecMsg.index('MPH:') + len('MPH:'):-1]
            self._windData.append(float(MyWindSpeedMPH))
            # TODO beaufort https://en.wikipedia.org/wiki/Beaufort_scale
        elif "RAIN_DETECT" in RecMsg:
            if self._isRainInit:
                self._isRainInit = False
            else:
                self._NodeControl.log.debug("rain tip over event")
                if self._NodeControl.DBCursor is not None:
                    try:
                        self._NodeControl.DBCursor.execute('INSERT INTO precipitation VALUES (?)',(datetime.datetime.now(),))
                        self._NodeControl.DBConn.commit()
                    except Exception, exp:
                        self._NodeControl.log.error("Error updating database, error: %s." % traceback.format_exc())
                else:
                    self._NodeControl.log.warning("No DBCursor found, can not write")
        elif "WIND_DIRECTION:ARB:":
            myWindDir = RecMsg[RecMsg.index('ARB:') + len('ARB:')-1]
            self._NodeControl.setProperty('curr-winddir', myWindDir)
        """
        rain We have a variable rain that is a counter for the amount of rainfall. 
        We then have a function (cb) that adds the bucket amount to it, the CALIBRATION variable which for this gauge 
        is 0.2794 mm per tip.
        """

# -*- coding: utf-8 -*-
import string
import traceback
from twisted.internet import reactor
import BMP085 as BMP085
import Adafruit_DHT


RAINTIPVOLUME = 0.2794
STATIONELEVATION=8.7

def doUpdate(NodeControl):
    NodeControl.log.debug("Weather Status update")
    try:
        # DS18B20
        if NodeControl.nodeProps.has_option('sensordata', 'GrondSensorPath'):
            mySensorReading = getDS18B20Temp(NodeControl, NodeControl.nodeProps.get('sensordata', 'GrondSensorPath'))
            if mySensorReading is not None:
                sGrondTemp = '{:.1f}'.format(mySensorReading  / float(1000))
                NodeControl.log.debug("Grond temperatuur: %s" % sGrondTemp)
                NodeControl.MQTTPublish(sTopic="buiten/grond", sValue=str(sGrondTemp), iQOS=0, bRetain=True)
            else:
                NodeControl.log.warning("no reading: %s" % NodeControl.nodeProps.get('sensordata', 'GrondSensorPath'))
        else:
            NodeControl.log.warning("Can not read buiten/grond, no [sensordata] GrondSensorPath configured")
        #BMP085
        try:
            sensor = BMP085.BMP085()
            Temp = '{:.1f}'.format(sensor.read_temperature())
            rawPress = sensor.read_sealevel_pressure(altitude_m=STATIONELEVATION) # sensor.read_pressure() # read_sealevel_pressure
            rawPresNum = int(rawPress)
            combinedPress = "{0}.{1}".format(rawPresNum / 100, rawPresNum % 100)
            formattedPress = '{:.1f}'.format(float(combinedPress))

            # NodeControl.MQTTPublish(sTopic="weer/temp", sValue=str(Temp), iQOS=0, bRetain=False)
            NodeControl.MQTTPublish(sTopic="weer/luchtdruk", sValue=str(formattedPress), iQOS=0, bRetain=True)
        except Exception, exp:
            NodeControl.log.warning("Error pressure status update, error: %s." % (traceback.format_exc()))

        # Wind
        if NodeControl.getProperty('curr-windspeed') is not None:
            NodeControl.MQTTPublish(sTopic="weer/wind-gem", sValue=str(NodeControl.getProperty('curr-windspeed')),
                                    iQOS=0, bRetain=False)
            # TODO "weer/wind-gem"
        # Wind richting
        if NodeControl.getProperty('curr-winddir') is not None:
            NodeControl.MQTTPublish(sTopic="weer/wind-richt", sValue=str(NodeControl.getProperty('curr-winddir')),
                                    iQOS=0, bRetain=False)
        # Rain
        # NodeControl.MQTTPublish(sTopic="weer/rain", sValue=str(csvRow[10]), iQOS=0, bRetain=True)
        # TODO is raining wanneer waarde max x sec oud is
        RainEvents24H = getXHPrecipitation(NodeControl, 24)
        if RainEvents24H is not None:
            Rain24H = '{:.1f}'.format(RainEvents24H * RAINTIPVOLUME)
            NodeControl.MQTTPublish(sTopic="weer/rain-24h", sValue=str(Rain24H), iQOS=0, bRetain=True)

        RainEvents1H = getXHPrecipitation(NodeControl, 1)
        if RainEvents1H is not None:
            Rain1H = '{:.1f}'.format(RainEvents1H * RAINTIPVOLUME)
            NodeControl.MQTTPublish(sTopic="weer/rain-1h", sValue=str(Rain1H), iQOS=0, bRetain=True)

        currentRain = isRaining(NodeControl)
        if currentRain is not None:
            myValue = "0"
            if currentRain:
                myValue = "1"
            NodeControl.MQTTPublish(sTopic="weer/rain", sValue=str(myValue), iQOS=0, bRetain=True)
        """      NodeControl.MQTTPublish(sTopic="weer/wind-gem", sValue=str(csvRow[7]), iQOS=0, bRetain=True)
                NodeControl.MQTTPublish(sTopic="weer/wind-max", sValue=str(csvRow[8]), iQOS=0, bRetain=True)
        """

        # DHT22
        if NodeControl.nodeProps.has_option('sensordata', 'DHT22Pin'):
            try:
                getDHT22Data(NodeControl, NodeControl.nodeProps.get('sensordata', 'DHT22Pin'), 0)
            except Exception, exp:
                NodeControl.log.warning("Error temp/hum status update, error: %s." % (traceback.format_exc()))
        else:
            NodeControl.log.warning("Can not read DHT sensor, no [sensordata] DHT22Pin configured")
        # UV Index TODO

    except Exception, exp:
        NodeControl.log.warning("Error weather status update, error: %s." % (traceback.format_exc()))

def getDHT22Data(NodeControl, Pin, iTry):
    sensor = Adafruit_DHT.DHT22
    humidity, temperature = Adafruit_DHT.read_retry(sensor, Pin)
    if humidity is not None and temperature is not None:
        if ( ( (temperature > -30) and  (temperature < 60) ) and
             ( (humidity > 0) and (humidity < 101) ) ):
            Temp = '{:.1f}'.format(temperature)
            Hum = '{:.1f}'.format(humidity)
            NodeControl.MQTTPublish(sTopic="weer/temp", sValue=str(Temp), iQOS=0, bRetain=True)
            NodeControl.MQTTPublish(sTopic="weer/hum", sValue=str(Hum), iQOS=0, bRetain=True)
    else:
        if iTry < 15:
            reactor.callLater(2, getDHT22Data, NodeControl, Pin, iTry+1)

def getDS18B20Temp(NodeControl, sSensorPath):
    mytemp = None
    try:
        f = open(sSensorPath, 'r')
        line = f.readline() # read 1st line
        crc = line.rsplit(' ', 1)
        crc = crc[1].replace('\n', '')
        if crc == 'YES':
            line = f.readline() # read 2nd line
            mytemp = line.rsplit('t=', 1)
        else:
            NodeControl.log.warning(
                "Error reading sensor, path: %s, error: %s." % (sSensorPath, 'invalid message'))
        f.close()
        if mytemp is not None:
            return int(mytemp[1])
        else:
            return None
    except Exception, exp:
        NodeControl.log.warning("Error reading sensor, path: %s, error: %s." % (sSensorPath, traceback.format_exc()))
        return None

def getXHPrecipitation(NodeControl, PeriodInHours):
    mySQL = "SELECT Count(*) FROM precipitation WHERE preDatetime >= datetime('now', '-%i hours', 'localtime')" % PeriodInHours
    try:
        return NodeControl.DBCursor.execute(mySQL).fetchone()[0]
    except Exception, exp:
        NodeControl.log.warning("Error reading getXHPrecipitation. Error: %s." % traceback.format_exc())
        return None

def isRaining(NodeControl):
    mySQL = "SELECT Count(*) FROM precipitation WHERE preDatetime >= datetime('now', '-300 seconds', 'localtime')"
    try:
        return NodeControl.DBCursor.execute(mySQL).fetchone()[0]
    except Exception, exp:
        NodeControl.log.warning("Error reading isRaining. Error: %s." % traceback.format_exc())
        return None


def checkDevices():
    # TODO
    # checks if all devices are found (does NOT check valid readings)

    allDevicesFound = False
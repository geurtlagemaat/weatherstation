import os
import traceback

import datetime
from twisted.internet import reactor
from twisted.internet import task

try:
    import RPi.GPIO as GPIO
except:
    pass

import weatherStatus
from SerialBusMaster import SerialBusMaster
from bliknetlib import nodeControl
import pytz
from astral import Astral, Location

oNodeControl = None

def setupGPIO():
    if os.name == 'posix':
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(23, GPIO.OUT)
        GPIO.setup(24, GPIO.OUT) # garden lights

def checkLights():
    if oNodeControl.nodeProps.has_option('gardenlightswitching', 'active') and \
            oNodeControl.nodeProps.getboolean('gardenlightswitching', 'active'):
        if not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'lat')):
            oNodeControl.log.error('setting not found: gardenlightswitching | lat, can not init.')
        elif not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'long')):
            oNodeControl.log.error('setting not found: gardenlightswitching | long, can not init.')
        elif not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'elev')):
            oNodeControl.log.error('setting not found: gardenlightswitching | elev, can not init.')
        elif not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'localtimezone')):
            oNodeControl.log.error('setting not found: gardenlightswitching | localtimezone, can not init.')
        elif not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'city')):
            oNodeControl.log.error('setting not found: gardenlightswitching | city, can not init.')
        elif not (oNodeControl.nodeProps.has_option('gardenlightswitching', 'country')):
            oNodeControl.log.error('setting not found: gardenlightswitching | country, can not init.')
        else:
            a = Astral()
            a.solar_depression = 'civil'
            l = Location((oNodeControl.nodeProps.get('gardenlightswitching', 'city'),
                          oNodeControl.nodeProps.get('gardenlightswitching', 'country'),
                          oNodeControl.nodeProps.get('gardenlightswitching', 'lat'),
                          oNodeControl.nodeProps.get('gardenlightswitching', 'long'),
                          oNodeControl.nodeProps.get('gardenlightswitching', 'localtimezone'),
                          oNodeControl.nodeProps.get('gardenlightswitching', 'elev')))
            mySun = l.sun()
            oNodeControl.log.debug('Dawn: %s.' % str(mySun['dawn']))
            oNodeControl.log.debug('Sunrise: %s.' % str(mySun['sunrise']))
            oNodeControl.log.debug('Sunset: %s.' % str(mySun['sunset']))
            oNodeControl.log.debug('Susk: %s.' % str(mySun['dusk']))
            oNodeControl.log.debug("Current time %s." % str(datetime.datetime.now()))
            if datetime.datetime.now(pytz.timezone(oNodeControl.nodeProps.get('gardenlightswitching', 'localtimezone'))) > mySun['sunrise'] and \
                datetime.datetime.now(pytz.timezone(oNodeControl.nodeProps.get('gardenlightswitching', 'localtimezone'))) < mySun['dusk']:
                GPIO.output(24, 0)
            elif datetime.datetime.now(pytz.timezone(oNodeControl.nodeProps.get('gardenlightswitching', 'localtimezone'))) > mySun['dusk']:
                GPIO.output(24, 1)

def cleanPrecipitationTable():
    oNodeControl.log.info("cleanPrecipitationTable")
    if oNodeControl.DBCursor is not None:
        sql = "DELETE FROM precipitation WHERE preDatetime <= date('now','-2 day', 'localtime')"
        oNodeControl.DBCursor.execute(sql)
        oNodeControl.DBConn.commit()
        oNodeControl.log.info("cleanPrecipitationTable done")

def checkDB():
    if oNodeControl.DBCursor is not None:
        try:
            sql = "CREATE TABLE IF NOT EXISTS 'precipitation' ( `preDatetime` TIMESTAMP NOT NULL, PRIMARY KEY(`preDatetime`) )"
            oNodeControl.DBCursor.execute(sql)
        except Exception, exp:
            oNodeControl.log.error("Error creating tables. Error %s." % traceback.format_exc())

def eUpdateWeather():
    checkLights()
    weatherStatus.doUpdate(oNodeControl)

# MQTT Things
def onMQTTSubscribe(client, userdata, mid, granted_qos):
    oNodeControl.log.info("Subscribed: " + str(mid) + " " + str(granted_qos))

def onMQTTMessage(client, userdata, msg):
    oNodeControl.log.info("ON MESSAGE:" + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
    if (msg.topic == "weer/updatecmd"):
        eUpdateWeather()

def subscribeTopics():
    if oNodeControl.mqttClient is not None:
        oNodeControl.mqttClient.on_subscribe = onMQTTSubscribe
        oNodeControl.mqttClient.subscribe("weer/updatecmd", 0);
        oNodeControl.mqttClient.on_message = onMQTTMessage
        oNodeControl.mqttClient.loop_start()

if __name__ == '__main__':
    now = datetime.datetime.now()
    oNodeControl = nodeControl.nodeControl(r'settings/bliknetnode.conf')
    oNodeControl.log.info("BliknetNode: %s starting at: %s." % (oNodeControl.nodeID, now))

    setupGPIO()
    checkDB()

    l = task.LoopingCall(cleanPrecipitationTable)
    l.start(86400)

    if oNodeControl.nodeProps.has_option('serial', 'active') and \
            oNodeControl.nodeProps.getboolean('serial', 'active'):
        if not (oNodeControl.nodeProps.has_option('serial', 'port')):
            oNodeControl.log.error('serial port not found (serialbus/port), can not init.')
        elif not (oNodeControl.nodeProps.has_option('serial', 'baudrate')):
            oNodeControl.log.error('serial baudrate not found (serialbus/baudrate), can not init.')
        else:
            SerialBusMaster = SerialBusMaster(oNodeControl)
    else:
        oNodeControl.log.info("Serial Bus not active.")

    # weather upload task
    if oNodeControl.nodeProps.has_option('weather', 'active') and \
            oNodeControl.nodeProps.getboolean('weather','active'):
        iWeatherUploadInt = 20
        if oNodeControl.nodeProps.has_option('weather', 'uploadInterval'):
            iWeatherUploadInt = oNodeControl.nodeProps.getint('weather', 'uploadInterval')
        oNodeControl.log.info("Weather upload task active, upload interval: %s" % str(iWeatherUploadInt))
        l = task.LoopingCall(eUpdateWeather)
        l.start(iWeatherUploadInt)
    else:
        oNodeControl.log.info("Weather upload task not active.")

    subscribeTopics()

    if oNodeControl.nodeProps.has_option('watchdog', 'circusWatchDog'):
        if oNodeControl.nodeProps.getboolean('watchdog', 'circusWatchDog') == True:
            oNodeControl.circusNotifier.start()
    reactor.run()
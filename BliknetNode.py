# -*- coding: utf-8 -*-
import os
import traceback
import datetime
import time

from RPi_AS3935 import RPi_AS3935
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
AS3935Sensor = None

def lightningInterrupt(channel):
    time.sleep(0.003)
    # global AS3935Sensor
    reason = AS3935Sensor.get_interrupt()
    if reason == 0x01:
        oNodeControl.log.debug("Noise level too high - adjusting")
        AS3935Sensor.raise_noise_floor()
    elif reason == 0x04:
        oNodeControl.log.debug("Disturber detected - masking")
        AS3935Sensor.set_mask_disturber(True)
    elif reason == 0x08:
        distance = AS3935Sensor.get_distance()
        oNodeControl.log.debug("We sensed lightning! It was %s km away" % str(distance) )
        oNodeControl.MQTTPublish(sTopic="lightning/distance", sValue=str(distance), iQOS=0, bRetain=False)

def setupGPIO():
    if os.name == 'posix':
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(23, GPIO.OUT)
        GPIO.setup(24, GPIO.OUT) # garden lights
        GPIO.setup(27, GPIO.IN)

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
            try:
                city = oNodeControl.nodeProps.get('gardenlightswitching', 'city')
                country = oNodeControl.nodeProps.get('gardenlightswitching', 'country')
                lat = oNodeControl.nodeProps.get('gardenlightswitching', 'lat')
                long = oNodeControl.nodeProps.get('gardenlightswitching', 'long')
                localtimezone = oNodeControl.nodeProps.get('gardenlightswitching', 'localtimezone')
                elev = oNodeControl.nodeProps.get('gardenlightswitching', 'elev')
                a = Astral()
                a.solar_depression = 'civil'
                l = Location()
                l.name = city
                l.region = country
                if "°" in lat:
                    l.latitude = lat # example: 51°31'N parsed as string
                else:
                    l.latitude = float(lat) #  make it a float

                if "°" in long:
                    l.longitude = long
                else:
                    l.longitude = float(long)

                l.timezone = localtimezone
                l.elevation = elev
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
            except Exception, exp:
                oNodeControl.log.error("checkLights init error. Error %s." % (traceback.format_exc()))

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
    # setupAS3935Sensor()
    try:
        AS3935Sensor = RPi_AS3935(address=0x03, bus=1)

        AS3935Sensor.set_indoors(False)
        AS3935Sensor.set_noise_floor(0)
        # TODO: calibrate needed ? sensor.calibrate(tun_cap=0x0F)
        AS3935Sensor.calibrate(tun_cap=0x06) # TODO move to settings
        oNodeControl.log.info("Sensor calibration done")
        GPIO.add_event_detect(27, GPIO.RISING, callback=lightningInterrupt)
    except Exception, exp:
        oNodeControl.log.error("Error during AS3935 init. Error %s." % (traceback.format_exc()))
    l = task.LoopingCall(cleanPrecipitationTable)
    l.start(86400)

    if oNodeControl.nodeProps.has_option('serial', 'active') and \
            oNodeControl.nodeProps.getboolean('serial', 'active'):
        if not (oNodeControl.nodeProps.has_option('serial', 'port')):
            oNodeControl.log.error('serial port not found (serialbus/port), can not init.')
        elif not (oNodeControl.nodeProps.has_option('serial', 'baudrate')):
            oNodeControl.log.error('serial baudrate not found (serialbus/baudrate), can not init.')
        else:
            try:
                SerialBusMaster = SerialBusMaster(oNodeControl)
            except Exception, exp:
                oNodeControl.log.error("SerialBusMaster init failed. Error %s." % (traceback.format_exc()))
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

    GPIO.output(23, 0)
    GPIO.output(24, 0)

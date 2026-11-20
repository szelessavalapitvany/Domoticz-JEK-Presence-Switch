"""
Jelenlet Kapcsolo python plugin for Domoticz
Author: szelessav,
Version: 1.0.0 (majus 25, 2025) 
"""
"""
<plugin key="JEK" name="Jelenlét Kapcsoló" author="szelessav" version="1.0.0">
	<description>
		<h2>Jelenlét Kapcsoló / Presence Switch</h2><br/>
	<br/>
	<br/>
		Jelenlét érzékelő segítségéval automatikusan kapcsolhatók eszközök. / Devices can be switched on automatically using a presence sensor.
	<br/>
	<br/>
		<strong><a href="#/Custom/JEK_Jelenlet_kapcsolo_Show_switch">HTML setup!</a></strong> (Csak már létező modulhoz!/Only for existing modules!)
	<br/>
	<br/>
	</description>
	<params>
		<param field="Address" label="Domoticz IP Address" width="200px" required="true" default="192.168.1.1"/>
		<param field="Port" label="Port" width="40px" required="true" default="8080"/>
		<param field="Username" label="Username" width="200px" required="false" default=""/>
		<param field="Password" label="Password" width="200px" required="false" default=""/>
		<param field="Mode1" label="Érkezéskor ON /  On arrival ON (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode2" label="Érkezéskor OFF / OFF upon arrival (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode3" label="Távozáskor ON / When leaving ON (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode4" label="Távozáskor OFF / When leaving, OFF (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode5" label="Jelenlét neve / Presence name (opciónális érték)" width="200px" required="false" default=""/>
		<param field="Mode6" label="Logging Level" width="200px">
			<options>
				<option label="Normal" value="Normal"  default="true"/>
				<option label="Verbose" value="Verbose"/>
				<option label="Debug - Python Only" value="2"/>
				<option label="Debug - Basic" value="62"/>
				<option label="Debug - Basic+Messages" value="126"/>
				<option label="Debug - Connections Only" value="16"/>
				<option label="Debug - Connections+Queue" value="144"/>
				<option label="Debug - All" value="-1"/>
			</options>
		</param>
	</params>
</plugin>
"""
import Domoticz
import json
from urllib import parse, request
from datetime import datetime, timedelta
import time
import math
import base64
import itertools
import re
import os
import heapq

class deviceparam:

	def __init__(self, unit, nvalue, svalue):
		self.unit = unit
		self.nvalue = nvalue
		self.svalue = svalue

class switchparam:

	def __init__(self, idx, command):
		self.idx = idx
		self.command = command

class TranslationLoader:

	def __init__(self, language="en"):
		self.translations = self.load_translations(language)
		if not self.translations:
			Domoticz.Debug("An error occurred while loading the translations!")
			self.translations = self.load_translations("en") 

	def load_translations(self, language):
		file_path = os.path.join(Parameters["HomeFolder"], f'jek_translate_{language}.json')
		try:
			with open(file_path, 'r', encoding='utf-8') as file:
				return json.load(file)
		except (FileNotFoundError, json.JSONDecodeError) as e:
			Domoticz.Debug(f"Error loading the file '{file_path}': {e}")
			return {} 

	def t(self, text):
		return self.translations.get(text, text)  # If there is no translation, it returns with the original text

class BasePlugin:

	def __init__(self):

		self.debug = True
		self.jelenlet = None
		self.jelenletInfo = False
		self.lastjelenletInfo = False
		self.loglevel = None
		self.statussupported = True
		self.nextupdate = datetime.now()
		self.erkezes_on = []
		self.erkezes_off = []
		self.tavozas_on = []
		self.tavozas_off = []
		return


	def onStart(self):

		self.location = Settings["Location"].split(";")
		
		tl = TranslationLoader(Parameters["Language"])
		
		# paraméterek szétbontása
		params = parseCSVparams(Parameters["Mode5"])
		self.jelenlet = params[0]

		# állítsa be a megfelelő naplózási szintet
		try:
			debuglevel = int(Parameters["Mode6"])
		except ValueError:
			debuglevel = 0
			self.loglevel = Parameters["Mode6"]
		if debuglevel != 0:
			self.debug = True
			Domoticz.Debugging(debuglevel)
			DumpConfigToLog()
			self.loglevel = "Verbose"
		else:
			self.debug = False
			Domoticz.Debugging(0)

		# ellenőrizze, hogy a gazdagép domoticz verziója támogatja-e a Domoticz.Status() python keretfüggvényt
		try:
			Domoticz.Status("This version of domoticz allows status logging by the plugin (in verbose mode)")
		except Exception:
			self.statussupported = False

		# hozza létre a gyermekeszközöket, ha ezek még nem léteznek
		devicecreated = []
		if 1 not in Devices:
			Options = {"LevelActions": "||",
				"LevelNames": tl.t("Off | Automatic switching"),
				"LevelOffHidden": "false",
				"SelectorStyle": "0"}
			Domoticz.Device(Name=tl.t("Presence-based switch"), Unit=1, TypeName="Selector Switch", Switchtype=18, Image=18, Options=Options, Used=1).Create()
			devicecreated.append(deviceparam(1, 0, "0"))
		if 2 not in Devices:
			Domoticz.Device(Name="On arrival ON", Unit=2, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(2, 0, "Off"))
		if 3 not in Devices:
			Domoticz.Device(Name="On arrival OFF", Unit=3, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(3, 0, "Off"))
		if 4 not in Devices:
			Domoticz.Device(Name="When leaving ON", Unit=4, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(4, 0, "Off"))
		if 5 not in Devices:
			Domoticz.Device(Name="When leaving OFF", Unit=5, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(5, 0, "Off"))

		# ha bármilyen eszközt hoztak létre az onStart()-ban, itt az ideje frissíteni az alapértelmezett beállításait
		for device in devicecreated:
			Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

		# listát készit a kapcsolókrol
		self.erkezes_on = parseCSV(Parameters["Mode1"])
		self.erkezes_off = parseCSV(Parameters["Mode2"])
		self.tavozas_on = parseCSV(Parameters["Mode3"])
		self.tavozas_off = parseCSV(Parameters["Mode4"])

		Domoticz.Error("erkezes_on={} erkezes_off={} tavozas_on={} tavozas_off={}".format(self.erkezes_on, self.erkezes_off, self.tavozas_on, self.tavozas_off))

	def onStop(self):
		Domoticz.Debugging(0)


	def onCommand(self, Unit, Command, Level, Color):

		Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

		nvalue = 1 if Level > 0 else 0
		svalue = str(Level)

		Devices[Unit].Update(nValue=nvalue, sValue=svalue)

		if Unit == 1: # újrainditás, ha megváltozik a vezérlésimód
			self.nextupdate = datetime.now()
			self.onHeartbeat()


	def onHeartbeat(self):

		self.now = datetime.now()

		self.switchJelenlet()

		self.lastjelenletInfo = self.jelenletInfo

		if Devices[1].sValue == "0":  # Kikapcsolva
			Domoticz.Debug("vezerlo kikapcsolva")


		elif Devices[1].sValue == "10":  # Automata mód
			Domoticz.Debug("automata mod")
			if self.jelenletInfo == True:
				self.switch_erkezes_on()
				self.switch_erkezes_off()
			else:
				self.switch_tavozas_on()
				self.switch_tavozas_off()


	def switchJelenlet(self):

		if self.jelenlet :
			self.jelenletInfo = JelenletAPI(self.jelenlet)
			Domoticz.Debug("jelenletInfo: "+format(self.jelenletInfo))

	def switch_erkezes_on(self):

		if not self.erkezes_on:
			return

		# A kapcsoló aktuális állapotonak beállítása és annak ellenőrzésére, hogy már a kívánt állapotban van-e
		switches = {}
		devicesAPI = DomoticzAPI(
			"type=devices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)
		if devicesAPI:
			for device in devicesAPI["result"]:  # elemzi a kapcsolóeszközt
				idx = int(device["idx"])
				if idx in self.erkezes_on: 
					if "Status" in device:
						switches[idx] = "On" if device["Status"] == "On" else "Off"
						Domoticz.Debug("switch_erkezes_on {} currently is '{}'".format(idx, device["Status"]))
					else:
						Domoticz.Error("Device with idx={} does not seem to be a switch !".format(idx))

		if len(switches) == 0:
			Domoticz.Error("none of the devices in the parameter is a switch... no action !")
			return

		# szükség szerint kapcsolja be/ki
		command = "On"
		Domoticz.Debug("Switch '{}'".format(command))
		for idx in self.erkezes_on:
			if switches[idx] != "On":  # ellenőrizze, hogy szükség van-e intézkedésre
				DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd={}".format(idx, command))

		if format(command) == "On":
			nvalue = 1
			svalue = "On"
		else :
			nvalue = 0
			svalue = "Off"
		
		Devices[2].Update(nValue=nvalue, sValue=svalue)

	def switch_tavozas_on(self):

		if not self.tavozas_on:
			return

		# A kapcsoló aktuális állapotonak beállítása és annak ellenőrzésére, hogy már a kívánt állapotban van-e
		switches = {}
		devicesAPI = DomoticzAPI(
			"type=devices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)
		if devicesAPI:
			for device in devicesAPI["result"]:  # elemzi a kapcsolóeszközt
				idx = int(device["idx"])
				if idx in self.tavozas_on: 
					if "Status" in device:
						switches[idx] = "On" if device["Status"] == "On" else "Off"
						Domoticz.Debug("Switch {} currently is '{}'".format(idx, device["Status"]))
					else:
						Domoticz.Error("Device with idx={} does not seem to be a switch !".format(idx))

		if len(switches) == 0:
			Domoticz.Error("none of the devices in the parameter is a switch... no action !")
			return

		# szükség szerint kapcsolja be/ki
		command = "On"
		Domoticz.Debug("Switch '{}'".format(command))
		for idx in self.tavozas_on:
			if switches[idx] != "On":  # ellenőrizze, hogy szükség van-e intézkedésre
				DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd={}".format(idx, command))

		if format(command) == "On":
			nvalue = 1
			svalue = "On"
		else :
			nvalue = 0
			svalue = "Off"
		
		Devices[3].Update(nValue=nvalue, sValue=svalue)

	def switch_erkezes_off(self):

		if not self.erkezes_off:
			return

		# A kapcsoló aktuális állapotonak beállítása és annak ellenőrzésére, hogy már a kívánt állapotban van-e
		switches = {}
		devicesAPI = DomoticzAPI(
			"type=devices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)
		if devicesAPI:
			for device in devicesAPI["result"]:  # elemzi a kapcsolóeszközt
				idx = int(device["idx"])
				if idx in self.erkezes_off: 
					if "Status" in device:
						switches[idx] = "On" if device["Status"] == "On" else "Off"
						Domoticz.Debug("Switch {} currently is '{}'".format(idx, device["Status"]))
					else:
						Domoticz.Error("Device with idx={} does not seem to be a switch !".format(idx))

		if len(switches) == 0:
			Domoticz.Error("none of the devices in the parameter is a switch... no action !")
			return

		# szükség szerint kapcsolja be/ki
		command = "Off"
		Domoticz.Debug("Switch '{}'".format(command))
		for idx in self.erkezes_off:
			if switches[idx] != "Off":  # ellenőrizze, hogy szükség van-e intézkedésre
				DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd={}".format(idx, command))

		if format(command) == "On":
			nvalue = 1
			svalue = "On"
		else :
			nvalue = 0
			svalue = "Off"
		
		Devices[4].Update(nValue=nvalue, sValue=svalue)

	def switch_tavozas_off(self):

		if not self.tavozas_off:
			return

		# A kapcsoló aktuális állapotonak beállítása és annak ellenőrzésére, hogy már a kívánt állapotban van-e
		switches = {}
		devicesAPI = DomoticzAPI(
			"type=devices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)
		if devicesAPI:
			for device in devicesAPI["result"]:  # elemzi a kapcsolóeszközt
				idx = int(device["idx"])
				if idx in self.tavozas_off: 
					if "Status" in device:
						switches[idx] = "On" if device["Status"] == "On" else "Off"
						Domoticz.Debug("Switch {} currently is '{}'".format(idx, device["Status"]))
					else:
						Domoticz.Error("Device with idx={} does not seem to be a switch !".format(idx))

		if len(switches) == 0:
			Domoticz.Error("none of the devices in the parameter is a switch... no action !")
			return

		# szükség szerint kapcsolja be/ki
		command = "Off"
		Domoticz.Debug("Switch '{}'".format(command))
		for idx in self.tavozas_off:
			if switches[idx] != "Off":  # ellenőrizze, hogy szükség van-e intézkedésre
				DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd={}".format(idx, command))

		if format(command) == "On":
			nvalue = 1
			svalue = "On"
		else :
			nvalue = 0
			svalue = "Off"
		
		Devices[5].Update(nValue=nvalue, sValue=svalue)

	def WriteLog(self, message, level="Normal"):

		if (self.loglevel == "Verbose" and level == "Verbose") or level == "Status":
			if self.statussupported:
				Domoticz.Status(message)
			else:
				Domoticz.Log(message)
		elif level == "Normal":
			Domoticz.Log(message)


global _plugin
_plugin = BasePlugin()


def onStart():
	global _plugin
	_plugin.onStart()


def onStop():
	global _plugin
	_plugin.onStop()


def onCommand(Unit, Command, Level, Color):
	global _plugin
	_plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
	global _plugin
	_plugin.onHeartbeat()


# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):

	listvals = []
	i=0
	for value in strCSV.split(","):
		try:
			val = int(value)
		except:
			pass
		else:
			listvals.append(val)
		i+=1
	return listvals

def parseCSVparams(strCSV):

	listvalsparams = []
	i=0
	for value in strCSV.split(","):
		try:
			val = str(value)
		except:
			pass
		else:
			listvalsparams.append(val)
		i+=1
	return listvalsparams


def DomoticzAPI(APICall):

	resultJson = None
	url = "http://{}:{}/json.htm?{}".format(Parameters["Address"], Parameters["Port"], parse.quote(APICall, safe="&="))
	Domoticz.Debug("Calling domoticz API: {}".format(url))
	try:
		req = request.Request(url)
		if Parameters["Username"] != "":
			Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
			credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
			encoded_credentials = base64.b64encode(credentials.encode('ascii'))
			req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

		response = request.urlopen(req)
		if response.status == 200:
			resultJson = json.loads(response.read().decode('utf-8'))
			if resultJson["status"] != "OK":
				Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
				resultJson = None
		else:
			Domoticz.Error("Domoticz API: http error = {}".format(response.status))
	except:
		Domoticz.Error("Error calling '{}'".format(url))
	return resultJson


# Generic helper functions
def DumpConfigToLog():
	for x in Parameters:
		if Parameters[x] != "":
			Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
	Domoticz.Debug("Device count: " + str(len(Devices)))
	for x in Devices:
		Domoticz.Debug("Device:" + str(x) + " - " + str(Devices[x]))
		Domoticz.Debug("Device ID: '" + str(Devices[x].ID) + "'")
		Domoticz.Debug("Device Name: '" + Devices[x].Name + "'")
		Domoticz.Debug("Device nValue: " + str(Devices[x].nValue))
		Domoticz.Debug("Device sValue: '" + Devices[x].sValue + "'")
		Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
	return


def JelenletAPI(jelennev):
	
	resultJelen = False
	
	try:
		url = "http://{}/cgi-bin/luci/wifi-presence/{}".format(Parameters["Address"], jelennev)
		Domoticz.Debug("Calling jelenletAPI: {}".format(url))
		req = request.Request(url)
		response = request.urlopen(req)
		if response.status == 200:
			resultJelen = json.loads(response.read().decode('utf-8'))
			if response.read().strip().decode("utf-8") == "true":
				resultJelen = True
		else:
			Domoticz.Error("JelenletAPI: http error = {}".format(response.status))
		response.close()
	except:
		Domoticz.Error("Error calling '{}'".format(url))
	
	if resultJelen != True :
		try:
			wifiurl = "http://{}/cgi-bin/luci/presence/{}".format(Parameters["Address"], jelennev)
			Domoticz.Debug("Calling jelenletAPI: {}".format(wifiurl))
			reqwifi = request.Request(url)
			response = request.urlopen(req)
			if response.status == 200:
				resultJelen = json.loads(response.read().decode('utf-8'))
				if response.read().strip().decode("utf-8") == "true":
					resultJelen = True
			else:
				Domoticz.Error("JelenletAPI: http error = {}".format(response.status))
			response.close()
		except:
			Domoticz.Error("Error calling '{}'".format(url))
		

	return resultJelen

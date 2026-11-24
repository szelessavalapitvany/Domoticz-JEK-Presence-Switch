var hardwareReq   = "/json.htm?type=command&param=gethardware";
var tempReq       = "/json.htm?type=command&param=graph&sensor=temp&range=day&idx=";
var tempName      = "/json.htm?type=command&param=getdevices&filter=temp&order=Name";
var switchReq     = "/json.htm?type=command&param=getlightlog&range=day&idx=";
var switchName    = "/json.htm?type=command&param=getdevices&filter=lightlog&order=Name";
var devicesReq    = "/json.htm?type=command&param=getdevices";
var PercentageReq = "/json.htm?type=command&param=graph&sensor=Percentage&range=day&idx=";
var utilityReq    = "/json.htm?type=command&param=graph&sensor=counter&range=day&idx=";
var windReq       = "/json.htm?type=command&param=graph&sensor=wind&range=day&idx=";
var setpointReq   = "/json.htm?type=command&param=getdevices&rid=";
var settingsReg   = "/json.htm?type=command&param=getsettings";

if (typeof window.JelenKontroller === 'undefined') {
	class JelenKontroller {
		constructor() {
			this.name = "";
		}
	}
	window.JelenKontroller = JelenKontroller;
}

if (typeof window.Jelen === 'undefined') {
	class Jelen {
		constructor() {
			this.historic=undefined;
			this.isDimmer=false;
		}
	}
	window.Jelen = Jelen;
}

Date.prototype.yyyymmdd_hhmm = function() {
	var mm = this.getMonth() + 1; // getMonth() is zero-based
	var dd = this.getDate();
	var hh = this.getHours();
	var mm = this.getMinutes();

	return [this.getFullYear(),
		(mm>9 ? '' : '0') + mm,
		(dd>9 ? '' : '0') + dd,
		'_',
		(hh>9 ? '' : '0') + hh,
		(mm>9 ? '' : '0') + mm
		].join('');
};

function getRequestParam(name){
	var req = location.search;
	if(req.length == 0) {
		req = location.href;
	}
	if(name=(new RegExp('[?&]'+encodeURIComponent(name)+'=([^&]*)')).exec(req))
		return decodeURIComponent(name[1]);
}

var hardwareNameAkt = [];
var pluginRequest = proto + address + ":" + port.toString() + "/json.htm?type=command&param=gethardware";
var allUsedIdxSet = new Set();
var allUsedIdxArray = [];

const extraModeConfig = {
	"DSVT_HMV_ZONE_12": [1, 2, 3, 4, 5],
	"NkV": [3, 4],
	"ASC": [2]
};

function prepareUsedIdxSet() {
	var extraIdxMap = {};  // Extra → [idx számok]

	$.ajax({
		url: pluginRequest,
		async: false,
		success: function(hwresult) {
			hwresult.result.forEach(function(hw) {
				const extraKey = typeof hw.Extra === "string" ? hw.Extra.trim() : null;

				if (hw.Type === 94 && hw.Enabled === "true" && extraKey && extraModeConfig.hasOwnProperty(extraKey)) {
					if (!(extraKey in extraIdxMap)) {
						extraIdxMap[extraKey] = new Set();
					}

					const allowedModes = extraModeConfig[extraKey];
					allowedModes.forEach(function(modeIndex) {
						const modeValue = hw["Mode" + modeIndex];
						if (typeof modeValue === "string" && modeValue.trim() !== "") {
							const parts = modeValue.split(",");
							parts.forEach(part => {
								const value = part.includes(":") ? part.split(":")[1] : part;
								const num = parseInt(value);
								if (!isNaN(num)) {
									extraIdxMap[extraKey].add(num);
								}
							});
						}
					});
				}
			});

			// Egyesítés: feltöltjük a globális Set-et
			allUsedIdxSet = new Set();  // újratelepítjük
			Object.values(extraIdxMap).forEach(arr => {
				arr.forEach(idx => allUsedIdxSet.add(idx));
			});
			allUsedIdxArray = Array.from(allUsedIdxSet).sort((a, b) => a - b);

			//console.log("Extra → idx számok:", extraIdxMap);
			//console.log("Összes használt idx:", allUsedIdxArray);
		}
	});
}


prepareUsedIdxSet();

var jelen = [];

function getJelen() {
	nodata = true;
	var langakt = "en"; // Alapértelmezett nyelv
	var request = proto + address + ":" + port.toString() + hardwareReq;
	var jelenObj = [];
	$.ajax({
		url: request,
		async: false,
		success: function (result) {
			for (var i = 0; i < result.result.length; i++) {
				if (result.result[i].Extra == "JEK" && result.result[i].Enabled == "true") {
					nodata = false;
					var jelenObj = new Jelen();
					var name = result.result[i].Name;
					jelenObj.name = name;
					jelenObj.id = result.result[i].idx;
					var minDate = 0;
					var innerRequest = proto + address + ":" + port.toString() + devicesReq;
					$.ajax({
						url: innerRequest,
						async: false,
						success: function (resultJelen) {
							jelenObj.host = result.result[i].Address
							jelenObj.uname = result.result[i].Username
							jelenObj.pass = result.result[i].Password
							jelenObj.port = result.result[i].Port
							jelenObj.Mode1 = result.result[i].Mode1;
							jelenObj.Mode2 = result.result[i].Mode2;
							jelenObj.Mode3 = result.result[i].Mode3;
							jelenObj.Mode4 = result.result[i].Mode4;
							jelenObj.Mode5 = result.result[i].Mode5;
							jelenObj.Mode6 = result.result[i].Mode6;
							
							request = proto + address + ":" + port.toString() + switchName;
							//console.log(request)
							$.ajax({
								url: request,
								async: false,
								success: function (resultswitchName) {
									jelenObj.switchnameakt = [];
									resultswitchName.result.forEach(function (item) {
										if (
											Number(item.Used) === 1 &&
											item.SwitchType &&
											item.SwitchType.toLowerCase().includes('on/off') &&
											!allUsedIdxSet.has(Number(item.idx))
										) {
											jelenObj.switchnameakt.push(item.Name + ':' + item.idx);
										}
									});
									//console.log("kapcsolók:", jelenObj.switchnameakt);
								}
							});

							var resultOnOn = [];
							for (var j = 0; j < resultJelen.result.length; j++) {
								if (jelenObj.id == resultJelen.result[j].HardwareID && resultJelen.result[j].Unit == 2) {

									request = proto + address + ":" + port.toString() + switchReq + resultJelen.result[j].idx;
									console.log(request);

									$.ajax({
										url: request,
										async: false,
										success: function (logresult) {
											resultOnOn = (logresult && Array.isArray(logresult.result)) ? logresult.result : [];
											jelenObj.onon = resultOnOn;

											if (resultOnOn.length) {
												minDate = Math.min.apply(null,
													resultOnOn.map(function (item) {
														return new Date(item.d);
													})
												);
											}
										}
									});
								}
							}


							var resultOnOff = [];
							for (var j = 0; j < resultJelen.result.length; j++) {
								if (jelenObj.id == resultJelen.result[j].HardwareID && resultJelen.result[j].Unit == 3) {

									request = proto + address + ":" + port.toString() + switchReq + resultJelen.result[j].idx;

									$.ajax({
										url: request,
										async: false,
										success: function (logresult) {
											resultOnOff = (logresult && Array.isArray(logresult.result)) ? logresult.result : [];
											jelenObj.onoff = resultOnOff;

											if (resultOnOff.length) {
												minDate = Math.min.apply(null,
													resultOnOff.map(function (item) {
														return new Date(item.d);
													})
												);
											}
										}
									});
								}
							}
							//console.log("OnOff kapcsoló log tömb:", resultOnOff);

							var resultOffOn = [];
							for (var j = 0; j < resultJelen.result.length; j++) {
								if (jelenObj.id == resultJelen.result[j].HardwareID && resultJelen.result[j].Unit == 4) {

									request = proto + address + ":" + port.toString() + switchReq + resultJelen.result[j].idx;

									$.ajax({
										url: request,
										async: false,
										success: function (logresult) {
											resultOffOn = (logresult && Array.isArray(logresult.result)) ? logresult.result : [];
											jelenObj.offon = resultOffOn;

											if (resultOffOn.length) {
												minDate = Math.min.apply(null,
													resultOffOn.map(function (item) {
														return new Date(item.d);
													})
												);
											}
										}
									});
								}
							}
							//console.log("OffOn kapcsoló log tömb:", resultOffOn);

							var resultOffOff = [];
							for (var j = 0; j < resultJelen.result.length; j++) {
								if (jelenObj.id == resultJelen.result[j].HardwareID && resultJelen.result[j].Unit == 5) {

									request = proto + address + ":" + port.toString() + switchReq + resultJelen.result[j].idx;

									$.ajax({
										url: request,
										async: false,
										success: function (logresult) {
											resultOffOff = (logresult && Array.isArray(logresult.result)) ? logresult.result : [];
											jelenObj.offoff = resultOffOff;

											if (resultOffOff.length) {
												minDate = Math.min.apply(null,
													resultOffOff.map(function (item) {
														return new Date(item.d);
													})
												);
											}
										}
									});
								}
							}
							//console.log("OffOff kapcsoló log tömb:", resultOffOff);
						}
					});
					jelen.push(jelenObj);
					//console.log("jelenObj log tömb:", jelenObj);
				}
			}
		}
	});
	return jelen;
}




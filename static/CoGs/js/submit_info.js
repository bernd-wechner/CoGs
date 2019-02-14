// Basic Javascript to include in any page for it to submit to Django some client info. Specifically
// 3 items are sent to Django:
//
// timezone		- The TZ database timezone name
// utcoffset	- Positive being East of Greenwich
// location 	- in form "City, Country"
//
// They are submitted to a URL defined below whichhas the name 'post_client_info'
// which must be defined in urls.py of course and be backed by a small view which 
// receives and does something with the submission.
//
// The timezone data and location data are posted separately, as the first is fast and reliable,
// the second slower and less reliable (may not be available).

// GET_ variables used for getting the location of the client
// We will use the GeoNames free service: http://www.geonames.org/export/web-services.html#findNearby
const GET_INFO = new XMLHttpRequest();
const GET_URL = 'http://api.geonames.org/findNearbyJSON?username=CoGs&cities=cities15000&lat={lat}&lng={lon}';

// POST_ variables used for posting the timezone and location info to the server
const POST_INFO = new XMLHttpRequest();
const POST_RECEIVER = "{% url 'post_client_info' %}";
const POST_TYPE = "application/x-www-form-urlencoded";

// Django provides (and demands if the server implemts it) Cross Site Request Forgery (CSRF) protection 
// Django proveds us with a csrf_token which it wants to see in a POST submission or it will reject it.
// This how Django knows the POST came from this form here and not some other submitter. 
// The token comes as a HTML hidden form element, and we're building out own POST submission so
// need to extract the name and value and compose a URI (Uniform Resource Identifer).
const CSRF_field = '{% csrf_token %}';
const CSRF_name = CSRF_field.match( /name="(.*?)"/ )[1];
const CSRF_value = CSRF_field.match( /value="(.*?)"/ )[1];
const CSRF_uri = CSRF_name + "="  + encodeURI(CSRF_value);

// A function that is called when navigator.geolocation.getCurrentPosition returns (i.e. it's callback)
function GetInfoFromGeoNames(position) {
	const URL = GET_URL.replace("{lat}", position.coords.latitude).replace("{lon}", position.coords.longitude);
	GET_INFO.open("GET", URL, true);

	GET_INFO.onreadystatechange = function () {
	    if (this.readyState === 4 && this.status === 200) {
	        // the request is complete, parse data 
	        const response = JSON.parse(this.responseText);
	        const city = response.geonames[0].name;
	        const country = response.geonames[0].countryName;
	        const location = CSRF_uri + "&location=" + encodeURI(city + ", " + country);

			// Send the location to the server
			POST_INFO.open("POST", POST_RECEIVER, true);
			POST_INFO.setRequestHeader("Content-Type", POST_TYPE);
			POST_INFO.send(location);			
	    }
	};
	
	GET_INFO.send(null);
}		
	
// A functon bound to the DOMContentLoaded event to fire as soon as possible after a page
// oad to submit the timezone info to the serner and the location if we find it.
function SendInfoToServer() {
	const tz = jstz.determine().name();
	const utcoffset = -1 * (new Date().getTimezoneOffset());
	const info =  CSRF_uri + "&timezone=" + encodeURI(tz) + "&utcoffset=" + encodeURI(utcoffset);

	// Send the timezone info to the server
	POST_INFO.open("POST", POST_RECEIVER, true);
	POST_INFO.setRequestHeader("Content-Type", POST_TYPE);
	POST_INFO.send(info);
	
	// Geolocation can exhibit some latency in collection so HTML5 implements it with a callback
	// We'll post the location when it arrives. Also it means if ti fails for some reason to get
	// a geolocation it simply doesn't callback with one.
	if (navigator.geolocation)
	    navigator.geolocation.getCurrentPosition(GetInfoFromGeoNames);
}

document.addEventListener("DOMContentLoaded", SendInfoToServer);		

// Basic Javascript to include in any page for it to submit to Django some client info.
// Specifically 3 items are sent to Django:
//
// timezone     - The TZ database timezone name
// utcoffset    - Positive being East of Greenwich
// location     - in form "City, Country"
//
// They are submitted to a URL provided in the variable POST_RECEIVER,
// which must be defined in urls.py of course and be backed by a small
// view which receives and does something with the submission.
//
// The timezone data and location data are posted separately, as the first
// is fast and reliable, the second slower and less reliable (may not be available).
//
// We expect CSRF_field and POST_RECEIVER to be set in the including template!
// as we need both the URL to post to (POST_RECEIVER) and the CSRF (Cross-Site
// Request Forgery prvention) token that Django supplies and insists on hearing
// back in a PSOT request or it will not accept it (CSRF_feld).
//
// Also the 3 items are only submitted if they are changed from references that are
// supplied in:
//
// SESSION_timezone
// SESSION_utcoffset
// SESSION_location
//
// If these three values are stored in the Djnago Session, they have the lifespan of Django
// Session which is essentially  from the first page load indefinitely into the future (until
// such time as the session_id cookie is lost - that is, the session is attached ot one browser
// on one machine by a session_id cookie, and it has lifespan as long as that cookie - which is
// until it's removed.
//
// If a change is detected - typically only on the very first surf into the sute given the
// lifespan of Django sessions - then the page is reloaded so that it renders with timezone
// awareness. It the rendering view is smart enough to tell us it is timezone insensitive by
// providing a variable TIMEZONE_insensitive, we won't reload the page.

// GET_ variables used for getting the location of the client
// We will use the GeoNames free service: http://www.geonames.org/export/web-services.html#findNearby
const GET_INFO = new XMLHttpRequest();
const GET_URL = 'https://secure.geonames.org/findNearbyJSON?username=CoGs&cities=cities15000&lat={lat}&lng={lon}';

// POST_ variables used for posting the timezone and location info to the server
const POST_INFO = new XMLHttpRequest();
const POST_TYPE = "application/x-www-form-urlencoded";

// Django provides (and demands if the server implemts it) Cross Site Request Forgery (CSRF) protection
// Django proveds us with a csrf_token which it wants to see in a POST submission or it will reject it.
// This how Django knows the POST came from this form here and not some other submitter.
// The token comes as a HTML hidden form element, and we're building out own POST submission so
// need to extract the name and value and compose a URI (Uniform Resource Identifer).
const CSRF_name = CSRF_field.match( /name="(.*?)"/ )[1];
const CSRF_value = CSRF_field.match( /value="(.*?)"/ )[1];
const CSRF_uri = CSRF_name + "="  + encodeURI(CSRF_value);

// Maintain a global variable to communicate to rest of page if a Reload was requested
let TZ_RELOAD_FORCED = false;

// A function that is called when navigator.geolocation.getCurrentPosition returns (i.e. it's callback)
function GetInfoFromGeoNames(position) {
	const URL = GET_URL.replace("{lat}", position.coords.latitude).replace("{lon}", position.coords.longitude);
	GET_INFO.open("GET", URL, true);

	console.log(`ClientInfo:  lat=${position.coords.latitude}, lon=${position.coords.longitude}`);

	GET_INFO.onreadystatechange = function () {
		if (this.readyState === 4 && this.status === 200) {
			// the request is complete, parse data
			const response = JSON.parse(this.responseText);
			const city = response.geonames[0].name;
			const country = response.geonames[0].countryName;
			const location = city + ", " + country;
			const info = CSRF_uri + "&location=" + encodeURI(location);

			// Send the location to the server (only if it's changed)
			if (location != SESSION_location) {
				POST_INFO.open("POST", POST_RECEIVER, true);
				POST_INFO.setRequestHeader("Content-Type", POST_TYPE);
				POST_INFO.send(info);
			}
		}
	};

	GET_INFO.send(null);
}

function LocationRequestFailed(error) {
	console.log(`ClientInfo:  error=${error}`);
}

// A function bound to the DOMContentLoaded event to fire as soon as possible after a page
// oad to submit the timezone info to the serner and the location if we find it.
function SendInfoToServer() {
	const tz = jstz.determine().name();
	const utcoffset = -1 * (new Date().getTimezoneOffset());
	const info =  CSRF_uri + "&timezone=" + encodeURI(tz) + "&utcoffset=" + encodeURI(utcoffset);

	console.log(`ClientInfo:  tz=${tz}, utcoffset=${utcoffset}`);

	// Send the timezone info to the server (only if it's changed) - and reload the page once Django knows the timezone!
    //if (tz != SESSION_timezone || utcoffset != SESSION_utcoffset) {
		POST_INFO.open("POST", POST_RECEIVER, true);

		const TZ_RELOAD_FORCED = (tz !==  DJANGO_timezone) && (typeof TIMEZONE_insensitive === 'undefined' || !TIMEZONE_insensitive);
		if (TZ_RELOAD_FORCED) POST_INFO.onreadystatechange = function () { if (this.readyState === 4 && this.status === 200) document.location.reload(); }

		POST_INFO.setRequestHeader("Content-Type", POST_TYPE);
		POST_INFO.send(info);
    //}

	// Geolocation can exhibit some latency in collection so HTML5 implements it with a callback
	// We'll post the location when it arrives. Also it means if ti fails for some reason to get
	// a geolocation it simply doesn't callback with one.
	// This fails on localhost when debugging, in Firefox. Chrome seems to work:
	// 	https://stackoverflow.com/questions/9731963/navigator-geolocation-getcurrentposition-always-fail-in-chrome-and-firefox
	if (navigator.geolocation) {
		console.log(`ClientInfo:  requesting location ...`);
		navigator.geolocation.getCurrentPosition(GetInfoFromGeoNames, LocationRequestFailed);
	} else
		console.log('ClientInfo:  Geolocation not supported.');
}

// Send the info right way before the DOM is finished loading!
SendInfoToServer();

// We could wait till the DOM was loaded, but why bother waiting? This is how we'd fire up when the DOM was loaded.
//document.addEventListener("DOMContentLoaded", SendInfoToServer);

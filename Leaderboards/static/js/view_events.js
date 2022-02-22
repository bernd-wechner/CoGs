const dayname = {"0":"Sunday", "1":"Monday", "2":"Tuesday", "3":"Wednesday", "4":"Thursday", "5":"Friday", "6":"Saturday"};
const daynum =  _.invert(dayname);

let clipboard = new Copy_With_Style({ button: document.getElementById("btnCopy"),
 									  stylesheets: ["events.css", "tooltip.css", "default.css"],
									  element: document.getElementById("content"),
									  mode: "attribute",	
									  //defer: false,
									  //progress: true,
									  //triggers: ["button"], // "schedule", "observe"],
									  //log_HTML_to_console: true,
									  //log_performance: true,
									  //debug: true,
									  //classes_to_debug: ["tooltiptext"]
									  //styles_to_debug: ["background-color"]
									  //tags_to_debug: ["canvas"]
									}); 

function show_url() { URLopts().then( (uo) => {const url = url_events.replace(/\/$/, "") + uo; window.history.pushState("","", url); clipboard.copy(window.location); } ) };

async function URLopts() {
	// GOTCHA: If we intend on using any of these selectors' values we run a real risk of not 
	// seeing what they should contain because of the ajax call used to populated them. It may 
	// not have returned yet. To wit, if we are waiting for any data we now have to wait for 
	// it or we can't build the URL options from the form data.
	await until(finished_waiting)

	// Get the values of the multiselect specifiers
	const leagues      = $('#leagues').val();
	const locations    = $('#locations').val();
	
	// Get the values of the date range 
	const date_from    = $('#date_from').val();
	const date_to      = $('#date_to').val();

	// Get the values of the event duration range 
	const duration_min = $('#duration_min').val();
	const duration_max = $('#duration_max').val();
	
	// Get the value of the event gap minimum
	const gap_days     = $('#gap_days').val();
	
	// Get the selected weekdays
	const checked_days = Array.from(document.querySelectorAll('input[name=days]:checked'));
	const week_days = checked_days.map(cb => dayname[cb.value]).join(",");
	
	let opts = [];
	
	// Handle the list options
	const league_list = encodeList(leagues.join(","));
	if (league_list && league_list != defaults["leagues"]) opts.push("leagues="+league_list);
	
	const location_list = encodeList(locations.join(","));
	if (location_list && location_list != defaults["locations"]) opts.push("locations="+location_list);

	// Handle the date range options
	if (date_from && date_from != defaults["date_from"]) opts.push("date_from="+encodeDateTime(date_from));
	if (date_to && date_to != defaults["date_to"]) opts.push("date_to="+encodeDateTime(date_to));

	// Handle the event duration range options
	if (duration_min && duration_min != defaults["duration_min"]) opts.push("duration_min="+duration_min);
	if (duration_max && duration_max != defaults["duration_max"]) opts.push("duration_max="+duration_max);

	// And the event gap minimum
	if (gap_days && gap_days != defaults["gap_days"]) opts.push("gap_days="+gap_days);

	// Submit any weekday restrictions
	if (week_days && week_days != defaults["week_days"]) opts.push("week_days="+week_days);

	return "?" + opts.join("&");
}

const REQUEST = new XMLHttpRequest();
REQUEST.onreadystatechange = got_new_events;

async function refetchEvents() {
	URLopts().then( (urlopts) => {
		// Build the URL to fetch (AJAX)
		const url = url_json_events + urlopts;
		
		// Display the reloading icon requeste
		$("#reloading_icon").css("visibility", "visible");
		
		// Let everyone know we're waiting on leaderboards
		if (!("events" in waiting_for)) waiting_for["events"] = new Set();
		waiting_for["events"] = new Set([...waiting_for["events"], url]);

		// Send the request
		REQUEST.open("GET", url, true); 
		REQUEST.send(null);
	} ); 
};

function got_new_events() {
	if (REQUEST.readyState === 4 && REQUEST.status === 200){
		// Let everyone know we're not waiting any more
		const url = new URL(REQUEST.responseURL);
		const chop = new RegExp("^"+RegExp.escape(url.origin));
		const key = url.href.replace(chop, "");

		waiting_for["events"].delete(key);
		if (waiting_for["events"].size === 0) {
			delete waiting_for["events"]; // If the set is empty remove the entry in the dict
		}

		// the request is complete, parse data
		const response = JSON.parse(REQUEST.responseText);

		const events = response[0]; 
		const stats = response[1]; 
		const settings = response[2];
		players = response[3];
		frequency = response[4];

		// Update the controls from settings
		InitControls(settings);
		
		// Replace the tables
		$("#events").replaceWith(events);
		$("#stats").replaceWith(stats);
		TableSorter('events')

		// Update the Bokeh plot
		//This works, but using the barid is better, more logical (and works too)
		//const plot = Bokeh.documents[0].get_model_by_id(plotid)
		//const source = plot.renderers[0].data_source

		const bars = Bokeh.documents[0].get_model_by_id(barsid)
		const source = bars.data_source
		source.data.x = players;
		source.data.top = frequency;
		source.change.emit();
		
		// Hide all the reloading icons we're supporting
		$("#reloading_icon").css("visibility", "hidden");		
	}
};

function InitWeekDays(values) {
	const day_chks = Array.from(document.querySelectorAll('input[name=days]'));
	if (values === undefined) {
		day_chks.forEach(cb => (cb.checked = false));
	} else {
		if (typeof values == "string") values = values.split(/\s*,\s*/);
		if (!Array.isArray(values)) return; // move on silently
		values = Number(values[0]) ? values : values.map(v => daynum[v]);
		day_chks.forEach(cb => (cb.checked = values.includes(cb.value)));
	}
}

function InitControls(settings) {
	// settings: a dictionary of settings to set the Controls to
	
	Select2Init($('#leagues'), settings.leagues);
	Select2Init($('#locations'), settings.locations);
	
	$('#date_from').val(settings.date_from);
	$('#date_to').val(settings.date_to);

	$('#duration_min').val(settings.duration_min);
	$('#duration_max').val(settings.duration_max);

	$('#gap_days').val(settings.gap_days);

	InitWeekDays(settings.week_days);
};

// Layout is driven by snapshots.
// 
// If we have one snapshot per game all is normal and we can just layout 
//    one board per game using cols as requested.
// If we have two snapshots per game max, then we're comparing two points in time
//    and snaphots can be presented in pairs. We can sort of respect cols as requested 
//    but each col has a pair of snapshots side by side for comparison so we'll ensure it's 
//    even (round up) and halve it to get about the requested number of columns.    
// If we have more than 2 snapshots per game we are looking at leaderboard timelines 
//    or evolutions and so want one game per row, and one column per snapshot, so we
//    can safely ignore cols, and use a table as wide as maxshots.   


// Configurable, should agree with what the view is configured to deliver.
// if the view is delivering baseline boards this should be true and we will
// not render them and use them only for calculating rank deltas. If it is false
// the view should idelaly not deliver baslines (or they'll render and not honor
// the leaderboard options accurately).
const use_baseline = true;
	
let boardcount = 0;
let maxshots = 0;
let totalshots = 0;
let boardshots = [];

// A converter of strings to booleans
String.prototype.boolean = function() {
    switch (this.toLowerCase()) {
      case true.toString():
        return true;
      case false.toString() :
        return false;
      default:
        throw new Error ("string.boolean(): Cannot convert string to boolean.");
    }
  };
  
function selectElementContents(el) {
      let body = document.body, range, sel;
      if (document.createRange && window.getSelection) {
          range = document.createRange();
          sel = window.getSelection();
          sel.removeAllRanges();
          try {
              range.selectNodeContents(el);
              sel.addRange(range);
          } catch (e) {
              range.selectNode(el);
              sel.addRange(range);
          }
      } else if (body.createTextRange) {
          range = body.createTextRange();
          range.moveToElementText(el);
          range.select();
      }
}

function copyStringToClipboard(str) {
   let el = document.createElement('textarea');
   el.value = str;
   el.setAttribute('readonly', '');
   el.style = {position: 'absolute', left: '-9999px'};
   document.body.appendChild(el);
   el.select();
   document.execCommand('copy');
   document.body.removeChild(el);
}  

function copyElementToClipboard(JQelement) {
	   let el = JQelement.clone().get(0);
	   el.setAttribute('readonly', '');
	   el.style = {position: 'absolute', left: '-9999px'};
	   document.body.appendChild(el);
	   selectElementContents(el);
	   document.execCommand('copy');
       document.body.removeChild(el);
}  

// We fetch new leaderboards via AJAX and so need to reappraise them when they
// arrive
function get_and_report_metrics(LB) {
	const metrics = leaderboard_metrics(LB); 

	// Globals that we'll set here
	boardcount = metrics[0]; // The number of games we are displaying
	maxshots   = metrics[1]; // We want to discover the widest game (maxium number of snapshots)
	totalshots = metrics[2]; // The total number of snapshots we'll be displaying
	boardshots = metrics[3]; // The number of snapshots on each leaderboard
	
	lblTotalCount = document.getElementById("lblTotalCount");
	lblTotalCount.innerHTML = "<b>" +  boardcount + "</b> leaderboards"; 
	
	lblSnapCount = document.getElementById("lblSnapCount");
	lblSnapCount.innerHTML = "(" + totalshots + " snapshots)";
	lblSnapCount.style.display = (totalshots > boardcount) ? "inline" : "none";
}

// But on first load we have leaderboards that were provided through context, so
// process those now
get_and_report_metrics(leaderboards);

// An initialiser for Select2 widgets used. Alas not so trivial to set
// as descrribed here:
// https://select2.org/programmatic-control/add-select-clear-items#preselecting-options-in-an-remotely-sourced-ajax-select2
function Select2Init(selector, values) {
	const selected = selector.val();
	let changed = false;

	for (let i = 0; i < values.length; i++)
		if (selected.indexOf(values[i].toString()) < 0) changed = true;
	
	if (changed) {
		selector.val(null).trigger('change');
		$.ajax({
		    type: 'GET',
		    url: url_selector.replace("__MODEL__", selector.prop('name')) + "?q=" + values
		}).then(function (data) {
			// data arrives in JSON like:
			// {"results": [{"id": "1", "text": "Bernd", "selected_text":
			// "Bernd"}, {"id": "2", "text": "Blake", "selected_text":
			// "Blake"}], "pagination": {"more": false}}
				
			for (let i=0; i<data.results.length; i++) {
			    // create the option and append to Select2
			    var option = new Option(data.results[i].text, data.results[i].id, true, true);
			    selector.append(option).trigger('change');
			}
	
		    // manually trigger the `select2:select` event
		    selector.trigger({
		        type: 'select2:select',
		        params: {
		            data: data
		        }
		    });
		});
	}
}

function dval(value, def) { return value !== undefined ? value : def; }

function InitControls(options) {	
	// We'll follow the same order as Leaderboards.views.leaderboard_options
	// This takes those same options provided in context (or from an ajx call)
	// as "options" and initialises the controls on the page.
	
	// Populate all the multi selectors
	// footnote: The league selector could be populated from game_leagues or
	// player_leagues
	// though they should typically be identical anyhow (albeit not guaranteed
	// to
	// be. If roundtripping from this form they will be, but a URL GET request
	// can
	// specify separate lists. We'll priritise game_leagues here.
	const players = _.union(options.game_players, options.players);
	Select2Init($('#games'), options.games);
	Select2Init($('#leagues'), options.game_leagues);
	Select2Init($('#players'), players);

	// ===================================================================================
	// Initialise the content options
	// ===================================================================================
	
	// Get the list of enabled options
	const enabled = options.enabled;
	
	const check_box_filters = options.game_filters.concat(options.player_filters);
	
	// and set all the checkboxes they map to:
	for (i = 0; i < check_box_filters.length; i++) {
		const opt = check_box_filters[i];

		// compare_back_to is a special option because we share it
		// between two radio buttons base on its value (int or date)
		const chk = (opt == "compare_back_to" && Number.isInteger(options.compare_back_to))
					? "#chk_num_days_ev"
				    : "#chk_" + opt;

		$(chk).prop('checked', enabled.includes(opt)).trigger('input');
	}

	// Disable any checkboxes that don't have supporting data
	// An option. I don't think it wise, as it might be nice to 
	// click the checkbox then ad the data for example. But the 
	// code rests here in case of  achnage of mind and as a model 
	// for how to do such things.
	const disable_options_lacking_data = false;
	
	if (disable_options_lacking_data) {
		const selected_games = $('#games').val();
		const selected_leagues = $('#leagues').val();
		const selected_players = $('#players').val();
		
		if (selected_games.length === 0)
		{
			$('#chk_games_ex').attr('disabled', true);
			$('#chk_games_in').attr('disabled', true);
		}
	
		if (selected_leagues.length === 0)
		{
			$('#chk_game_leagues_any').attr('disabled', true);
			$('#chk_game_leagues_all').attr('disabled', true);
			$('#chk_player_leagues_any').attr('disabled', true);
			$('#chk_player_leagues_all').attr('disabled', true);
		}
	
		if (selected_players.length === 0)
		{
			$('#chk_game_players_any').attr('disabled', true);
			$('#chk_game_players_all').attr('disabled', true);
			$('#chk_players_ex').attr('disabled', true);
			$('#chk_players_in').attr('disabled', true);
		}
	}

	// cols is special. It is on only respected when maxshots is 1. 
	// On any view with evolution it's not used disable it if it's 
	// not used.
	$('#cols').val(dval(options.cols, 1));
	$('#cols').attr('disabled', maxshots > 1);
	
	// Then the rest of the game selectors
	$('#num_games').val(options.num_games);         // Mirror of
													// #num_games_latest
	$('#num_games_latest').val(options.num_games);  // Mirror of #num_games
	$('#changed_since').val(options.changed_since);
	$('#num_days').val(options.num_days);	  		// Mirror of num_days_ev
	$('#num_days_ev').val(options.num_days);  		// Mirror of num_days

	// Then the player selectors
	$('#num_players_top').val(options.num_players_top);
	$('#num_players_above').val(options.num_players_above);
	$('#num_players_below').val(options.num_players_below);
	$('#min_plays').val(options.min_plays);
	$('#played_since').val(options.played_since);
	
	// ========================================================================
	// The perspective option
	$('#as_at').val(options.as_at);  	// undefined is fine here.

	// ========================================================================
	// Evolution options are driven by radio buttons (one only). And so we want
	// to set the
	// right radio button so to speak. We base this on the specified options.
	let evolution_selection = "no_evolution";
	if (options.compare_with) 
		evolution_selection = "compare_with";
	else if (options.compare_back_to && Number.isInteger(options.compare_back_to))
		evolution_selection = "num_days_ev";
	else if (options.compare_back_to)
		evolution_selection = "compare_back_to";
	
	$("input[name=evolution_selection][value="+evolution_selection+"]").prop('checked', true);
	
	// Then set the values in the Evolution selection area. The defaults are
	// fine
	// here if the options were deleteted by a shortcut button using
	// override_content
	// because it is the radio button that does the selecting anyhow. and the
	// minimal
	// content is selected above where we set the radio content.
	// Note that we are for historic snapshots minimizing the defaults for a a
	// shortcut
	// button that uses override_content. For the game and player filters
	// conversely
	// we maximized the view (all games and all players and no hostroic
	// snapshots is
	// the position we aim for).
	$('#compare_with').val(dval(options.compare_with, defaults.compare_with));
	
	// compare_back_to is in fact a content option we simply recycle here
	const cbt = dval(options.compare_back_to, defaults.compare_back_to); 
	if (Number.isInteger(cbt))
		$('#num_days_ev').val(cbt);
	else
		$('#compare_back_to').val(cbt);
	
	// ===================================================================================
	// Initialise the presentation options
	// ===================================================================================
	
	// We use dval to return a minimalist option if that option is undefined
	// we expect that to be the case for any shortcut button that uses the
	// override_presentation flag and doesn't set explicit values (to override
	// it with)
	// We want to use minimalist (disabled like) version not the defaults that
	// the server
	// provides in this case.
	
	// The the content formatting options
	$('#chk_highlight_players').prop('checked', dval(options.highlight_players, false))
	$('#chk_highlight_changes').prop('checked', dval(options.highlight_changes, false))
	$('#chk_highlight_selected').prop('checked', dval(options.highlight_selected, false))
	
	$('#names').val(dval(options.names, "nick"));	
	$('#links').val(dval(options.links, "none"));

	// Then the extra info options for leaderboard headers
	$('#chk_details').prop('checked', dval(options.details, false));
	$('#chk_analysis_pre').prop('checked', dval(options.analysis_pre, false));
	$('#chk_analysis_post').prop('checked', dval(options.analysis_post, false));
	$('#chk_show_delta').prop('checked', dval(options.show_delta, false));
	
	// And the admin options
	$('#chk_ignore_cache').prop('checked', dval(options.ignore_cache, false));

	// Add the shortcut buttons
	AddShortcutButtons()	
	
	// If we made the options static we want to copy them to address bare and
	// copy.paste buffer
	if (options.made_static) { show_url();}
}

function is_enabled(checkbox_id) {
	return $("input[id='"+checkbox_id+"']").is(":checked");
}

function encodeList(list) {
	return encodeURIComponent(list).replace(/%2C/g, ",");
}

function encodeDateTime(datetime) {
	// We communicate datetimes in the ISO 8601 format:
	// https://en.wikipedia.org/wiki/ISO_8601
	// but in URLs they turn into an ugly mess. If we make a few simple URL safe
	// substitutions and unmake them at the server end all is good, and URLs
	// become
	// legible approximations to ISO 8601.
	//
	// Of note:
	//
	// + is a standard way to encode a space in URL. Though encodeURIComponent
	// opts for %20.
	// we can use + safely and it arrives at server as a space.
	//
	// : is encoded as %3A. It turns out : is not a recommended URL character
	// and a
	// reserved character, but it does transport fine at least on Chrome tests.
	// Still we can substitue - for it and that is safe legible char already in
	// use on the dates and can be decoded back to : by the server.
	//
	// The Timezone is introduced by + or -
	//
	// - travels unhindered. Is a safe URL character.
	// + is encoded as %2B, but we can encode it with + which translates to a
	// space at the server, but known we did this it can decdoe the space back
	// to +.
	return encodeURIComponent(datetime).replace(/%20/g, "+").replace(/%3A/g, "-").replace(/%2B/g, "+");
}

function URLopts(make_static) {
	// The opposite so to speak of InitControls() here we read those same
	// controls and prepare URL options for self same to submit an AJAX 
	// request for updates (or simply display on the address bar if desired).
	//
	// make_static: just passes the same request to server to return the options
	// more static than we submit them. Mainly to do with latest event options
	// which will come back as pinned dates rather that relative to now.
	//
	// We want to submit the state of all controls somehow too so that when 
	// the URL generated with these options here is loaded the controls are 
	// initialised with options as they stand.
		
	// For the radio buttons we just fetch the selected value
	const evolution_selection = $("input[name='evolution_selection']:checked").val();
	
	// Then get the values of the three multiselect game specifierd
	const games   = $('#games').val().join(",");
	const leagues = $('#leagues').val().join(",");
	const players = $('#players').val().join(",");
	
	// Then the rest of the game selectors
	const num_games        = $('#num_games').val();
	const num_games_latest = $('#num_games_latest').val();
	const changed_since    = $("#changed_since").val();
	const num_days         = $('#num_days').val();
	const num_days_ev      = $('#num_days_ev').val();
	
	// Then the player selectors
	const num_players_top   = $('#num_players_top').val();
	const num_players_above = $('#num_players_above').val();
	const num_players_below = $('#num_players_below').val();
	const min_plays         = $('#min_plays').val();
	const played_since      = $('#played_since').val();
	
	// Then the perspective and snapshot selectors
	const as_at           = $('#as_at').val();
	const compare_with    = $('#compare_with').val();
	const compare_back_to = $('#compare_back_to').val();
	
	// The the content formatting options
	const highlight_players  = $('#chk_highlight_players').is(":checked");
	const highlight_changes  = $('#chk_highlight_changes').is(":checked");
	const highlight_selected = $('#chk_highlight_selected').is(":checked");

	// Then the extra info options for leaderboard headers
	const details       = $('#chk_details').is(":checked");
	const analysis_pre  = $('#chk_analysis_pre').is(":checked");
	const analysis_post = $('#chk_analysis_post').is(":checked");	
	const show_delta    = $('#chk_show_delta').is(":checked");	
	const show_baseline = $('#chk_show_baseline').is(":checked");	
	
	const names = $('#names').val();	
	const links = $('#links').val();

	// Then the leaderboard screen layout options
	const cols = $('#cols').val();
	
	// Now push all the selected option onto opts.
	// Always start with "no_defaults" as the defaults were used
	// to populate the controls when the page loaded. So if they've
	// been changed, we want to change them. The server should not
	// be using defaults on our AJAX request (they are just for
	// initial page load)
	let opts = ["no_defaults"];

	// TODO: Add a Location filter, so we can narrow
	// sessions down to games played at a given
	// location.
	//
	// TODO: Implement Tourneys and a Tourney filter.

	// Handle the Game list based options	
	const game_list = encodeList(games);

	if (game_list.length > 0) {
		let game_options = [];
	
		if      (is_enabled("chk_games_ex")) game_options.push("games_ex");
		else if (is_enabled("chk_games_in")) game_options.push("games_in");

		if (game_options.length > 0)
			for (i=0; i<game_options.length; i++) opts.push(game_options[i]+"="+game_list);
		else	
			// If no context supplied for the games, then submit them in the 
			// transport option (no filter, just transports the list to server 
			// for rendering the inital value of the games selector)
			opts.push("games="+game_list);
	}
	
	// Handle the Player list options
	const player_list = encodeList(players);
			
	// We submit the list of leagues in context if any context demands it
	// else in a basic form for transport to the server, to provide back in
	// template context for initialising the leagues selector.
	if (player_list.length > 0) {
		let player_options = [];

		// The first context to check is on the player filters
		if      (is_enabled("chk_players_ex")) player_options.push("players_ex");			
		else if (is_enabled("chk_players_in")) player_options.push("players_in");

		// The second context to check is on the game filters
		if      (is_enabled("chk_game_players_any")) player_options.push("game_players_any");
		else if (is_enabled("chk_game_players_all")) player_options.push("game_players_all");

		if (player_options.length > 0)
			for (i=0; i<player_options.length; i++) opts.push(player_options[i]+"="+player_list);
		else	
			// If no context supplied for the players, then submit them in the 
			// transport option (no filter, just transports the list to server 
			// for rendering the inital value of the players selector)
			opts.push("players="+player_list);
	}
	
	// Handle the League list options
	const league_list = encodeList(leagues);
	
	// We submit the list of leagues in context if any context demands it
	// else in a basic form for transport to the server, to provide back in
	// template context for initialising the leagues selector.
	if (league_list.length > 0) {
		let league_options = [];
		
		// The first context to check is on the game filters
		if      (is_enabled("chk_game_leagues_any")) league_options.push("game_leagues_any");
		else if (is_enabled("chk_game_leagues_all")) league_options.push("game_leagues_all");
	
		// The second  context to check is on the player filters
		     if (is_enabled("chk_player_leagues_any")) league_options.push("player_leagues_any");
		else if (is_enabled("chk_player_leagues_all")) league_options.push("player_leagues_all");

		if (league_options.length > 0)
			for (i=0; i<league_options.length; i++) opts.push(league_options[i]+"="+league_list);
		else	
			// If no context supplied for the leagues, then submit them in the 
			// transport option (no filter, just transports the list to server 
			// for rendering the inital value of the leagues selector)
			opts.push("leagues="+league_list);
	}
	
	// Handle the rest of the Game filters
	if (is_enabled("chk_top_games") && num_games)
		// We submit num_games with an integer to enable this option.
		// If num_games is not submited or 0, the server should not
		// consider a top_games request in force.
		opts.push("top_games="+encodeURIComponent(num_games));

	if (is_enabled("chk_latest_games") && num_games_latest)
		// We submit num_games with an integer to enable this option.
		// If num_games is not submited or 0, the server should not
		// consider a latest_games request in force.
		opts.push("latest_games="+encodeURIComponent(num_games_latest));	
	

	// Handle the rest of the Player filters
	if (is_enabled("chk_changed_since") && changed_since)
		// We submit changed_since with a date/time. If it's not submitted
		// or submitted as an empty string then the server should not be
		// enforcing a game_activity filter on games.
		opts.push("changed_since="+encodeDateTime(changed_since));			
	
	if (is_enabled("chk_num_days") && num_days)
		// We submit session_games as the length of the session in days, only if
		// it's checked and a value is provided. Server side can take presence
		// of
		// the option as request to enforce it and should not enforce the filter
		// if it's absent. This is a special filter which finds the last session
		// of any game played (in the filtered list above) from now or as_at
		// and subtracts num_days and returns the games played in that window
		// of days. Used to get quick results on a games night or weekend or
		// other event.
		opts.push("num_days="+encodeURIComponent(num_days));
	
	if (is_enabled("chk_num_players_top") && num_players_top)
		// If we want to show only the top n players on every leaderboard this
		// is the
		// option. As ever, the server should take submission of the option as a
		// request
		// to filter players by it, and absence as a request not to apply that
		// filter.
		opts.push("num_players_top="+encodeURIComponent(num_players_top));		
		
	if (is_enabled("chk_num_players_above") && num_players_above) 
		// If a player list is provided a further option of showing a number
		// of players above any selected player. As usual submitted only if
		// enabled and a value provided and lack of submission asks server
		// not to display any.
		opts.push("num_players_above="+encodeURIComponent(num_players_above));		
		
	if (is_enabled("chk_num_players_below") && num_players_below)	
		// If a player list is provided a further option of showing a number
		// of players below any selected player. As usual submitted only if
		// enabled and a value provided and lack of submission asks server
		// not to display any.
		opts.push("num_players_below="+encodeURIComponent(num_players_below));		
		
	if (is_enabled("chk_min_plays") && min_plays)
		// We submit a request to show only players who have played at least a
		// certain number of times on the leaderboard. This a means of filtering
		// out the players who've only played once or twice from the crowd.
		// Submitting a number requests they be filtered out, not submitting it
		// asks server not to filter players based on play count.
		opts.push("min_plays="+encodeURIComponent(min_plays));		
		
	if (is_enabled("chk_played_since") && played_since)
		// We submit also if request an option to filter on recent activity.
		// Basically a way to say, we want to filter out anyone who hasn't
		// played a game in the last period of interest, to grab a leaderboard
		// of currently active players.
		opts.push("played_since="+encodeDateTime(played_since));		
			
	// Then the perspective option
	if (as_at)
		// We submit the the persepective request (pretend the submitted date is
		// 'now', basically)
		opts.push("as_at="+encodeDateTime(as_at))

	// And the evolution option
	switch(evolution_selection) {
		// Evolution asks each leaderboard to be presented with one or more
		// historic leaderboards so we can see the change in the leaderboards 
		// each session produces (the default leaderboard is of course the one 
		// current (now or as_at). But in this case only one option makes sense. 
		// The default is of course "nothing" and we submit nothing if that is selected.
	  case "compare_with":
		  	if (compare_with)
		  		// We submit a number of past session to compare the current one
				// with
		  		opts.push("compare_with="+encodeURIComponent(compare_with));
			break;
	  case "compare_back_to":
		  	if (compare_back_to)
		  		// We submit a a date to compare back to. We want to compare
				// back to the last session before this date as it created 
				// the leaderboard in effect at this date.
				if (compare_back_to == changed_since)
		  			opts.push("compare_back_to");
				else 
		  			opts.push("compare_back_to="+encodeDateTime(compare_back_to));
		    break;
	  case "num_days_ev":
			if (num_days_ev)
				// The partner to the game filter above is a back-to request
				// which asks to show all the leaderboard evolution during that
				// gaming event. So should present the leaderboard in effect 
				// when that event started and one after each game session during 
				// that event.
				//
				// We encode the number of days in the back-to request as a
				// plain int, as opposed to a date/time and this is how the 
				// server knows it's an event based request.
				if (num_days_ev == num_days)
					opts.push("compare_back_to");
				else
					opts.push("compare_back_to=" + encodeURIComponent(num_days_ev));
			break;
	}		
	
	// These have valid defaults, on or off, and we only have to submit
	// deviations from that default.
	if (highlight_players  != defaults.highlight_players) opts.push("highlight_players="+encodeURIComponent(highlight_players));
	if (highlight_changes  != defaults.highlight_changes) opts.push("highlight_changes="+encodeURIComponent(highlight_changes));
	if (highlight_selected != defaults.highlight_selected) opts.push("highlight_selected="+encodeURIComponent(highlight_changes));
	
	if (names != defaults.names) opts.push("names="+encodeURIComponent(names));
	if (links != defaults.links) opts.push("links="+encodeURIComponent(links));

	// Then the extra info options for leaderboard headers
	// These too have valid defaults, on or off, and we only have to submit
	// deviations from that default.
	if (details       != defaults.details)       opts.push("details="+encodeURIComponent(details));
	if (analysis_pre  != defaults.analysis_pre)  opts.push("analysis_pre="+encodeURIComponent(analysis_pre));
	if (analysis_post != defaults.analysis_post) opts.push("analysis_post="+encodeURIComponent(analysis_post));
	if (show_delta    != defaults.show_delta)    opts.push("show_delta="+encodeURIComponent(show_delta));
	if (show_baseline != defaults.show_baseline) opts.push("show_baseline="+encodeURIComponent(show_baseline));

	// Then the leaderboard screen layout options
	// This also has a valid default, and we only have to submit deviations from
	// that default.
	if (cols != defaults.cols) opts.push("cols="+encodeURIComponent(cols));		

	if (make_static) opts.push("make_static"); 
	
	// Finally the admin options
	const ignore_cache = $('#chk_ignore_cache').is(":checked");
	if (ignore_cache) opts.push("ignore_cache");
	
	return "?" + opts.join("&");
}

// TODO: We should fetch definitions from the database
// or better said, they should be delivered with leaderboards, based on the
// user logged on, with a default set for anonymous users.
// For now just hard coding a set of defaults.

// The 0th element is ignored, nominally there to represent the Reload button
// and because we prefer our shortcut buttons to number from 1.
// Global so that we can add them with one function and respond to them with 
// another.
let shortcut_buttons = [null]; 

// TODO: The aim here is to provide programable shortcut buttons. The general
// gist is that we've defined an array structure here, and we would have a default 
// set for anonymous users and for logged in users we'd get it passed in with the 
// AJAX leaderboards request or in the template on page load (as we do leaderboards), 
// for the logged in user.

// TODO: We need to code up a means of saving options. My thought is on the
// Advanced Options drop down, beside the Apply button is a "Save As Shortcut" 
// button, and beside it some controls, an int selector that runs 1 to the current 
// number of buttons plus one (so we can overwrite a given slot or create new one, 
// and two checkboxes, one for override_content, and one for override_presentation, 
// and then a name which should support template items like:
// {league} for the preferred league
// {leagues} for the selected league(s) - properly formated as "a,b,c and/or d"
// {players} for the selected player(s) - properly formated as "a,b,c and/or d"
// {games} for the selected game(s) - properly formated as "a,b,c and d"
// and of course when we add them {tourneys} and {locations} as well.
//
// These need to be saved to a Django model which is keyed on user and button ID
// (number) and possibly with context (leaderboards) so in future we can support
// programmable buttons on other views too.

function GetShortcutButtons() {
	pl_id = preferred_league[0];
	pl_name = preferred_league[1];
	
	// Start afresh
	shortcut_buttons = [null];
	
	shortcut_buttons.push(["All leaderboards", true, false, {"enabled": []}]);

	if (pl_id)
		shortcut_buttons.push([`All ${pl_name} leaderboards`, true, false, 
			{"enabled": ["player_leagues_any", "game_leagues_any"], 
			 "game_leagues": [pl_id]
			}]);

	shortcut_buttons.push(["Impact of last games night", true, false, 
		{"enabled": ["num_days", "compare_back_to"], 
	     "num_days": 1,
	     "compare_back_to": 1,
	     "num_players_top": 10,
		 "details": true,
		 "links": "BGG"
		}]);

	if (pl_id)
		shortcut_buttons.push([`Impact of last ${pl_name} games night`, true, false,  
			{"enabled": ["player_leagues_any", "game_leagues_any", "num_days", "compare_back_to"], 
			 "game_leagues": [pl_id],
		     "num_days": 1,
		     "compare_back_to": 1,
		     "num_players_top": 10,
			 "details": true,
			 "links": "BGG"
			}]);
	
	return shortcut_buttons;
}

function AddShortcutButtons() {
	shortcut_buttons = GetShortcutButtons();
	
	for (let id=1; id<shortcut_buttons.length; id++) {
		let label = shortcut_buttons[id][0];
		let button = $("#btnShortcut"+id);

		// If the button exists, just relabel it.
		if (button.length) {
			button.value = label;
			
		// Else add a new button.
		} else {
			$(".lo_shortcuts").append(`<button type="button" class="button_left" id="btnShortcut${id}" onclick="ShortcutButton(this)">${label}</button>`)
		}
	}		
}

function ShortcutButton(button) {
	const matches = button.id.match(/btnShortcut(\d+)/);
	const id = matches ? matches[1] : null;
	
	// null or 0 will return with no action
	if (!id) return; 

	// if not in legal range return as well
	if (id < 1 || id > shortcut_buttons.length) return;
	
	const def = shortcut_buttons[id];
	
	const override_content      = def[1];  // If true, override existing content options, else augment them
	const override_presentation = def[2];  // If true, override existing presentation options, else augment them
	const opts                  = def[3];  // The options to apply

	// Respect the two override flags when set, by deleting
	// any options there may be in the respective category.
	if (override_content) 
		for (let opt of options.content_options)
			delete options[opt]

	if (override_presentation) 
		for (let opt of options.presentation_options)
			delete options[opt]
	
	// We replace the options that the shortcut button demands
	for (let [ key, value ] of Object.entries(opts)) {
		options[key] = value;
		if (options.need_enabling.includes(key) && !options.enabled.includes(key)) 
			options.enabled.push(key) 		
	}
	// Reinitalise all the filter controls
	InitControls(options)

	// Reload the leaderboards
	refetchLeaderboards();
}

function toggle_visibility(class_name, visible_style) {
	current = $("."+class_name)[0].style.display;
	if (current == visible_style) 
		$("."+class_name).css('display', 'none');		
	else
		$("."+class_name).css('display', visible_style);
	$('.multi_selector').trigger('change');
}

function toggle_highlights(highlight_type, checkbox) {
	const tag = "highlight_" + highlight_type;

	const tag_on = tag + "_on"; 
	const tag_off = tag + "_off"; 
		
	if (checkbox.checked)
		$(".leaderboard."+tag_off).removeClass(tag_off).addClass(tag_on);
	else
		$(".leaderboard."+tag_on).removeClass(tag_on).addClass(tag_off);
}

// Some simple one-liner functions to handle input events
function blank_zero(me) { if (me.value == 0) me.value = ""; }
function check_check(me, boxes, unboxes) { $(boxes).prop('checked', Boolean(me.value)); if (unboxes && Boolean(me.value)) { $(unboxes).not(boxes).prop('checked', false);} }
function check_radio(me, name, value, fallback) { $("input[name='"+name+"'][value='"+(me.value?value:fallback)+"']").prop("checked",true); }
function only_one(me, others) {	if (me.checked)	$(others).not(me).prop('checked', false); }
function mirror(me, to, uncheck_on_zero) { $(to).val(me.value); if (uncheck_on_zero && me.value == 0) $(uncheck_on_zero).prop("checked",false); }
function copy_if_empty(me, to) { if ($(to).val() == '') $(to).val(me.value); }

function show_url() { const url = url_leaderboards.replace(/\/$/, "") + URLopts(); window.history.pushState("","", url); copyStringToClipboard(window.location); }
function show_url_static() { refetchLeaderboards(null, true); }

function enable_submissions(yes_or_no) {
	$("#leaderboard_options :input").prop("disabled", !yes_or_no);
	// When enabling them, reinitialise them (in case any are disabled during initialisation)
	if (yes_or_no) InitControls(options);
}

function got_new_leaderboards() {
	if (this.readyState === 4 && this.status === 200){
		// the request is complete, parse data
		const response = JSON.parse(this.responseText);

		// Capture response in leaderboards
		$('#title').html(response[0]); 
		$('#subtitle').html(response[1]); 
		options =  response[2]
		leaderboards = response[3];
		
		// Get the max and total for rendering
		get_and_report_metrics(leaderboards);

		// Update options
		InitControls(options);
		
		// redraw the leaderboards
		DrawTables("tblLB");
		
		// Hide all the reloading icons we're supporting
		$("#reloading_icon").css("visibility", "hidden");		
		$("#reloading_icon_advanced").css("visibility", "hidden");
		
		// Enable form elements again
		enable_submissions(true);
	}
};

const REQUEST = new XMLHttpRequest();
REQUEST.onreadystatechange = got_new_leaderboards;
	
function refetchLeaderboards(reload_icon, make_static) {
	if (typeof reload_icon === "undefined" || reload_icon == null) reload_icon = 'reloading_icon';
	if (typeof make_static === "undefined") make_static = false;
	
	// Build the URL to fetch (AJAX)
	const url = url_json_leaderboards + URLopts(make_static);
	
	// Display the reloading icon requeste
	$("#"+reload_icon).css("visibility", "visible");
	
	// Disable all the submission buttons
	enable_submissions(false);

	REQUEST.open("GET", url, true);
	REQUEST.send(null);
}

// Draw all leaderboards, sending to target and enabling links or not
function DrawTables(target, links) {
	// Oddly the jQuery forms $('#links') and $('#cols') fails here. Not sure
	// why.
	const selLinks = document.getElementById("links");	
	const selCols = document.getElementById("cols");
	let cols = parseInt(selCols.options[selCols.selectedIndex].text);	

	if (links == undefined) links = selLinks.value == "none" ? null : selLinks.value;

	const LB_options = [
		document.getElementById("chk_highlight_players").checked,
		document.getElementById("chk_highlight_changes").checked,
		document.getElementById("chk_highlight_selected").checked,
		document.getElementById("chk_details").checked,
		document.getElementById("chk_analysis_pre").checked,
		document.getElementById("chk_analysis_post").checked,
		document.getElementById("chk_show_delta").checked
	];
	
	// Get the list of players selected in the multi-select box #players
	const selected_players = $('#players').val().join(",");

	// The name format to use is selected in a #names selector
	const name_format  = $("#names").val();

	// maxshots is the maximum number of snapshots of any games's boards in the
	// database we're about to render. If it's 1 that implies no evolution is being 
	// displayed just a single snapshot per game.
	if (maxshots == 1) {
		var totalboards = leaderboards.length;		
		var rows = totalboards / cols;
		var remainder = totalboards - rows*cols;
		if (remainder > 0) { rows++; }

		// A wrapper table for the leaderboards
		var table = document.getElementById(target); 
		table.innerHTML = "";
		table.className = 'leaderboard wrapper'

		for (var i = 0; i < rows; i++) {
			var row = table.insertRow(i);
			for (var j = 0; j < cols; j++) {
				k = i*cols+j 
				if (k < totalboards) {
					var cell = row.insertCell(j);
					//cell.className = 'leaderboard wrapper'
					cell.appendChild(LeaderboardTable(leaderboards[k], 0, links, LB_options, selected_players, name_format));
				}
			}
		}
	} 
	else {
		// One row per board and its snapshots
		// Ignore cols and use our own value here
		cols = maxshots;
		rows = leaderboards.length;

		// A wrapper table for the leaderboards
		var table = document.getElementById(target); 
		table.innerHTML = "";
		table.className = 'leaderboard wrapper'

		var lb = 0; 
		for (var i = 0; i < rows; i++) {
			var row = table.insertRow(i);
			for (var j = 0; j < boardshots[lb]; j++) {
				var cell = row.insertCell(j);
				//cell.className = 'leaderboard wrapper'
				cell.appendChild(LeaderboardTable(leaderboards[lb], j, links, LB_options, selected_players, name_format));
			}
			lb++; 
		}			
	}			 
}

// ===================================================================================
// Attach event handlers to the Select2 widgets  
// (enabling and disabling dependent controls - checkboxes)
// ===================================================================================

$('#games').on("change", function(e) {
	const disable = $(this).val().length === 0;
	$('#chk_games_ex').attr('disabled', disable);
	$('#chk_games_in').attr('disabled', disable);
	
	if (disable) {
		$('#chk_games_ex').prop('checked', false);
		$('#chk_games_in').prop('checked', false);
	}
});

$('#leagues').on("change", function(e) {
	const disable = $(this).val().length === 0;
	$('#chk_game_leagues_any').attr('disabled', disable);
	$('#chk_game_leagues_all').attr('disabled', disable);
	$('#chk_player_leagues_any').attr('disabled', disable);
	$('#chk_player_leagues_all').attr('disabled', disable);

	if (disable) {
		$('#chk_game_leagues_any').prop('checked', false);
		$('#chk_game_leagues_all').prop('checked', false);
		$('#chk_player_leagues_any').prop('checked', false);
		$('#chk_player_leagues_all').prop('checked', false);
	}
});

$('#players').on("change", function(e) {
	const disable = $(this).val().length === 0;
	$('#chk_game_players_any').attr('disabled', disable);
	$('#chk_game_players_all').attr('disabled', disable);
	$('#chk_players_ex').attr('disabled', disable);
	$('#chk_players_in').attr('disabled', disable);

	if (disable) {
		$('#chk_game_players_any').prop('checked', false);
		$('#chk_game_players_all').prop('checked', false);
		$('#chk_players_ex').prop('checked', false);
		$('#chk_players_in').prop('checked', false);
	}
	
	// If the player list changes while highlight_selected is on we need 
	// to redraw the tables to render the highlights on the approriate players.
	const highlight_selected = $('#chk_highlight_selected').is(":checked");
	if (highlight_selected) DrawTables("tblLB");
});

// ===================================================================================
// Populate all the controls  
// ===================================================================================

InitControls(options);

// ===================================================================================
// Draw the leaderboard tables  
// ===================================================================================

DrawTables("tblLB");

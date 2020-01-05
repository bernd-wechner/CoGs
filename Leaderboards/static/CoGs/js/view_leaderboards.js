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
	
var boardcount = 0;
var maxshots = 0;
var totalshots = 0;

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
	let snapshots = 0; 

	// Globals that we'll set here
	boardcount = LB.length;
	maxshots = 0;
	totalshots = 0;
	
	for (let g=0; g<boardcount; g++) {
		snapshots = LB[g][3].length;
		totalshots += snapshots;
		if (snapshots > maxshots) maxshots = snapshots;
	}	 

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
	Select2Init($('#games'), options.games)
	Select2Init($('#leagues'), options.game_leagues)
	Select2Init($('#players'), options.game_players)

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

	// Then the leaderboard screen layout options
	$('#cols').val(dval(options.cols, 1));

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
	// but in URLS they turn into an ugly mess. If we make a few simple URL safe
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
	// The opposite so to speal of InitControls() here we read those same
	// controls and prepare
	// URL options for self same to submit an AJAX request for updates (or
	// simply display on
	// the address bar if desired).
	//
	// make_static: just passes the same request to server to return the options
	// more
	// static than we submit them. Mainly to do with latest event options
	// which will come back as pinned dates.
	//
	// Again we'll follow the same order as in InitControls and
	// Leaderboards.views.leaderboard_options
	// but in the URL we will only include values that deviate form the defaults
	// (in the interests of
	// brevity and efficiency. Also, the broader game and evolution only
	// submitting options relevant
	// to that option (again, for brevity and efficiency)
		
	// For the radio buttons we just fetch the selected value
	const evolution_selection = $("input[name='evolution_selection']:checked").val();
	
	// Then get the values of the three multiselect game specifierd
	const games = $('#games').val().join(",");
	const leagues = $('#leagues').val().join(",");
	const players = $('#players').val().join(",");
	
	// Then the rest of the game selectors
	const num_games = $('#num_games').val();
	const num_games_latest = $('#num_games_latest').val();
	const changed_since = $("#changed_since").val();
	const num_days = $('#num_days').val();
	const num_days_ev = $('#num_days_ev').val();
	
	// Then the player selectors
	const num_players_top = $('#num_players_top').val();
	const num_players_above = $('#num_players_above').val();
	const num_players_below = $('#num_players_below').val();
	const min_plays = $('#min_plays').val();
	const played_since = $('#played_since').val();
	
	// Then the perspective and snapshot selectors
	const as_at = $('#as_at').val();
	const compare_with = $('#compare_with').val();
	const compare_back_to = $('#compare_back_to').val();
	
	// The the content formatting options
	const highlight_players  = $('#chk_highlight_players').is(":checked");
	const highlight_changes  = $('#chk_highlight_changes').is(":checked");
	const highlight_selected = $('#chk_highlight_selected').is(":checked");

	// Then the extra info options for leaderboard headers
	const details = $('#chk_details').is(":checked");
	const analysis_pre = $('#chk_analysis_pre').is(":checked");
	const analysis_post = $('#chk_analysis_post').is(":checked");	
	
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

	// Start with the game filters:
	//
	// TODO: Add a Location filter, so we can narrow
	// sessions down to games played at a given
	// location.
	//
	// TODO: Implement Tourneys and a Tourney filter.
	if (is_enabled("chk_games_ex") && games)
		// An exclusive list of games if we asked for them.
		opts.push("games_ex="+encodeList(games));
	
	if (is_enabled("chk_games_in") && games)
		// An inclusive list of games if we asked for them.
		opts.push("games_in="+encodeList(games));

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
	
	const league_list = encodeList(leagues);
	// We submit the list of leagues only if an any or all request is in place
	// and
	// we use the name of the request to flag how to use the list. But it's one
	// or
	// the other and if neither is present no league list is submitted and no
	// league
	// filter should be applied at server end. The defaults should include
	// game_league_any = preferred_league from the session filter and that
	// should
	// see the chk_game_league_any checked when we initControls.
	if (is_enabled("chk_game_leagues_any") && leagues)
		opts.push("game_leagues_any="+league_list);	
	else if (is_enabled("chk_game_leagues_all") && leagues)
		opts.push("game_leagues_all="+league_list);

	const player_list = encodeList(players);		
	// We submit the list of players only if an any or all request is in place
	// and
	// we use the name of the request to flag how to use the list. But it's one
	// or
	// the other and if neither is present no league list is submitted and no
	// league
	// filter should be applied at server end.
	if (is_enabled("chk_game_players_any") && players)
		opts.push("game_players_any="+player_list);
	else if (is_enabled("chk_game_players_all") && players)
		opts.push("game_players_all="+player_list);

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
	
	// Then the player filters:
	if (is_enabled("chk_players_ex") && players)
		// If we want to show only selected players (exclusive).
		opts.push("players_ex="+player_list);			
	
	if (is_enabled("chk_players_in") && players)
		// If we want to forecfully include selected players.
		opts.push("players_in="+player_list);			

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
		
	// We submit the list of leagues only if an any or all request is in place
	// and
	// we use the name of the request to flag how to use the list. But it's one
	// or
	// the other and if neither is present no league list is submitted and no
	// league
	// filter should be applied at server end. The defaults should include
	// player_league_any = preferred_league from the session filter and that
	// should
	// see the chk_player_league_any checked when we initControls.
	if (is_enabled("chk_player_leagues_any") && leagues)
		opts.push("player_leagues_any="+league_list);
	if (is_enabled("chk_player_leagues_all") && leagues) 
		opts.push("player_leagues_all="+league_list);			
	
	// Then the perspective option
	if (as_at)
		// We submit the the persepective request (pretend the submitted date is
		// 'now', basically)
		opts.push("as_at="+encodeDateTime(as_at))

	// And the evolution option
	switch(evolution_selection) {
	  // Evolution asks each leaderboard to be presented ith one or more
		// historic leaderboards
	  // so we can see the change in the leaderboards each session produces
		// (the default
	  // leaderboard is of course the one current (now or as_at). But in this
		// case only one
	  // option makes sense. The default is of course "none" and we submit
		// nothing if that is
	  // selected.
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
		  		// The partner to the game filter above is a back to request
				// which asks to show
		  		// all the leaderboard evolution during that game session. So
				// should present
		  		// the leaderboard in effect when that session started and one
				// after each game
		  		// session in that broader session (not we use the term session
				// to denote the
		  		// play of one game and recording of its results or alternately
				// the play of a load
		  		// of games over a day or days ...).
		  		//
		  		// We encode the number of days in the back to request as a
				// plain int, as opposed
		  		// to a date/time and this is how the server knows it's a
				// session relative request.
				if (num_days_ev == num_days)
		  			opts.push("compare_back_to");
				else
		  			opts.push("compare_back_to=" + encodeURIComponent(num_days_ev));
		    break;
	}		
	
	// These have valid defaults, on or off, and we only have to submit
	// deviations from that default.
	if (highlight_players != defaults.highlight_players) opts.push("highlight_players="+encodeURIComponent(highlight_players));
	if (highlight_changes != defaults.highlight_changes) opts.push("highlight_changes="+encodeURIComponent(highlight_changes));
	if (highlight_selected != defaults.highlight_selected) opts.push("highlight_selected="+encodeURIComponent(highlight_changes));
	
	if (names != defaults.names) opts.push("names="+encodeURIComponent(names));
	if (links != defaults.links) opts.push("links="+encodeURIComponent(links));

	// Then the extra info options for leaderboard headers
	// These too have valid defaults, on or off, and we only have to submit
	// deviations from that default.
	if (details != defaults.details) opts.push("details="+encodeURIComponent(details));
	if (analysis_pre != defaults.analysis_pre) opts.push("analysis_pre="+encodeURIComponent(analysis_pre));
	if (analysis_post != defaults.details) opts.push("analysis_post="+encodeURIComponent(analysis_post));

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
// or better said, they should be delivered with eladerboards, based on the
// user logged on, with a default set for annonymous users.
// For now just hard coding a set of defaults.

// The 0th element is ignored, nominally there to represent the Reload button
// and because we prefer our shortcut buttons to number from 1
// Global so that we can add them with one function and respond to them with 
// another.
let shortcut_buttons = [null]; 

// TODO: The aim here is to provide programable shortcut buttons. The general
// gist is
// that we've defined an array structure here, and we would have a default set
// for
// anonymous users and for logged in users we'd get it passed in with the AJAX
// leaderboards
// request or in the template on page load (as we do leaderboards), for the
// logged in user.
// TODO: We need to code up a means of saving options. My thought is on the
// Advanced Options
// drop down, deside the Apply button is a "Save As Shortcut" button, and beside
// it some
// controls, an int selector that runs 1 to the current number of buttons plus
// one (so we can
// overwrite a given slot or create new one, and two checkboxes, one for
// override_content, and
// one for override_presentation, and then a name which should support template
// items like:
// {league} for the preferred league
// {leagues} for the selected league(s) - properly formated as "a,b,c and/or d"
// {players} for the selected player(s) - properly formated as "a,b,c and/or d"
// {games} for the selected game(s) - properly formated as "a,b,c and d"
// and of course when we add them {tourneys} and {locations} as well.
//
// These need to be saved to a Django model which is keyed on user and button ID
// (number)
// and possibly with context (leaderboards) so in future we can support
// programmable
// buttons on other views too.

function GetShortcutButtons() {
	// Start afresh
	shortcut_buttons = [null];
	
	shortcut_buttons.push(["All leaderboards", true, false, {"enabled": []}]);

	if (preferred_league[0])
		shortcut_buttons.push([`All ${preferred_league[1]} leaderboards`, true, false, 
			{"enabled": ["player_leagues_any", "game_leagues_any"], 
			 "game_leagues": [preferred_league[0]]
			}]);

	shortcut_buttons.push(["Impact of last games night", true, false, 
		{"enabled": ["num_days", "compare_back_to"], 
	     "num_days": 1,
	     "compare_back_to": 1,
	     "num_players_top": 10,
		 "details": true,
		 "links": "BGG"
		}]);

	if (preferred_league[0])
		shortcut_buttons.push([`Impact of last ${preferred_league[1]} games night`, true, false,  
			{"enabled": ["player_leagues_any", "game_leagues_any", "num_days", "compare_back_to"], 
			 "game_leagues": [preferred_league[0]],
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
	// TODO: We should consider if any others need changing!
	// Might be OK if enabled is simply overwritten. But maybe
	// not, the parser server-side may not look at enabled, but
	// look at other submissions. Needs diagnosis.
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

// Function to draw one leaderboard table
function LBtable(LB, snapshot, links) {
// LB is specific to one game and is a data structure that contains one board
// per snapshot,
// and each board is a list of players.
// In LB:
// First tier has just four values: Game PK, Game BGGid, Game name, Snapshots
// Second tier is Snapshots which is is a list of five values tuples: Date time
// string, count of plays, count of sessions, session details and Leaderboard
// Leaderboard is the third tier which is a list of tuples which have six
// values: Player PK, Player BGGid, Player name, Trueskill rating, Play count,
// Victory count

	// Column Indices in LB[3]:
	const iPKgame = 0;
	const iBGGid = 1;
	const iGameName = 2;
	const iSnapshots = 3;

	// The name format to use
	const name_choice  = $("#names").val();
	
	// Extract the data we need
	const pkg = LB[iPKgame];
	const BGGid = LB[iBGGid];
	const game = LB[iGameName];

	// This MUST align with the way ajax_Leaderboards() bundles up leaderboards
	// which in turn relies on Game.leaderboard to provide its tuples.
	//
	// Rather a complex structure that may benefit from some naming (rather than
	// being a list of lists of lists of lists. Must explore how dictionaries
	// map
	// into Javascript at some stage and consider a reimplementation.
	
	// Column Indices in LB[iSnapshots]:
	// index 0 holds the session PK, not needed here
	// (unless we want to put a link to the session somewhere later I guess).
	const iDateTime            = 1;
	const iPlayCount           = 2;
	const iSessionCount        = 3;
	const iSessionPlayers      = 4;
	const iSessionDetails      = 5;
	const iSessionAnalysisPre  = 6;
	const iSessionAnalysisPost = 7;
	const iPlayerList          = 8;
		
	// HTML values are let not const because we'll wrap selective contents with
	// links later
	// HTML values come paired with data values (which are ordered player list)
	const date_time                  = LB[iSnapshots][snapshot][iDateTime]
	const play_count                 = LB[iSnapshots][snapshot][iPlayCount];
	const session_count              = LB[iSnapshots][snapshot][iSessionCount];
	const session_players            = LB[iSnapshots][snapshot][iSessionPlayers];
	let   session_details_html       = LB[iSnapshots][snapshot][iSessionDetails][0];
	const session_details_data       = LB[iSnapshots][snapshot][iSessionDetails][1];
	let   session_analysis_pre_html  = LB[iSnapshots][snapshot][iSessionAnalysisPre][0];
	const session_analysis_pre_data  = LB[iSnapshots][snapshot][iSessionAnalysisPre][1];
	let   session_analysis_post_html = LB[iSnapshots][snapshot][iSessionAnalysisPost][0];
	const session_analysis_post_data = LB[iSnapshots][snapshot][iSessionAnalysisPost][1];
	const player_list                = LB[iSnapshots][snapshot][iPlayerList];
	
	// Get the index of the last snapshot, as that one is special
	// for now it means at least we can't highlight rank changes on that
	// snapshot
	const last_snapshot = LB[iSnapshots].length - 1;
	
	// Create the Game link based on the requested link target
	const linkGameCoGs = url_view_Game.replace('00',pkg);
	const linkGameBGG = "https:\/\/boardgamegeek.com/boardgame/" + BGGid;
	const linkGame = links == "CoGs" ? linkGameCoGs : links == "BGG" ?  linkGameBGG : null;

	// Fix the session detail and analysis headers which were provided with
	// templated links
	let linkPlayerCoGs = url_view_Player.replace('00','{ID}');
	let linkPlayerBGG = "https:\/\/boardgamegeek.com/user/{ID}";
	let linkTeamCoGs = url_view_Team.replace('00','{ID}');
	
	let linkRanker = {};
	linkRanker["Player"] = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;
	linkRanker["Team"] = links == "CoGs" ? linkTeamCoGs : links == "BGG" ?  null : null;

	// Build a map of PK to BGGid for all rankers
	// Note, session_details_data, session_analysis_pre_data and
	// session_analysis_post_data perforce
	// contain the same map (albeit in a different order) so we can use just one
	// of them to build the map.
	let linkRankerID = {}
	for (let r = 0; r < session_details_data.length; r++) {
		const PK = session_details_data[r][0];
		const BGGname = session_details_data[r][1];
		
		linkRankerID[PK] = links == "CoGs" ? PK : links == "BGG" ?  BGGname : null;
	}

	// A regex replacer which has as args first the matched string then each of
	// the matched subgroups
	// The subgroups we expect for a link update to the HTML headers are
	// klass, model, id and then the text.
	// This is a function that the following replace() functions pass matched
	// groups to and is tasked
	// with returning a the replacement string.
	function fix_template_link(match, klass, model, id, txt) {
		if (linkRankerID[id] == null) 
			return txt;
		else {
			var url = linkRanker[model].replace('{ID}', linkRankerID[id]);
			return "<A href='"+url+"' class='"+klass+"'>"+txt+"</A>";
		}
	}
	
	// Fix the links in the HTML headers
	// An example: {link.field_link.Player.1}Bernd{link_end}
	session_details_html = session_details_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	session_analysis_pre_html = session_analysis_pre_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	session_analysis_post_html = session_analysis_post_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
		
	// A regex replacer which has as args first the matched string then each of
	// the matched subgroups
	// The subgroups we expect from name update to the HTML headers are:
	// pk, nick, full, complete
	// We don't actually need the PK, it's just there.
	function fix_template_name(match, pk, nick, full, complete) {
	    switch (name_choice) {
	      case "nick": return nick;
	      case "full": return full;
	      case "complete": return complete;
	      default: throw new Error ("Illegal name selector.");
	    }
	}

	// Fix the names in the HTML headers
	// An example: "{1,Bernd,Bernd <Hidden>,Bernd <Hidden> (Bernd)}"
	session_details_html = session_details_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
	session_analysis_pre_html = session_analysis_pre_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
	session_analysis_post_html = session_analysis_post_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
	
	var table = document.createElement('TABLE');
	table.className = 'leaderboard'
	table.style.width = '100%';

	// Five header rows as follows:
	// A full-width session detail block, or the date the leaderboard was set
	// (of last session played that contributed to it)
	// A full-width pre session analysis
	// A full-width post session analysis
	// A game header with the name of the game (2 cols) and play/session summary
	// (3 cols)
	// A final header with 5 column headers (rank, player, rating, plays,
	// victories)

	var tableHead = document.createElement('THEAD');
	table.appendChild(tableHead);	    

	// #############################################################
	// First Header Row

	var tr = document.createElement('TR');
	tableHead.appendChild(tr);

	var th = document.createElement('TH');
	var content;
	if (linkGame) {
		content = document.createElement('a');
		content.setAttribute("style", "text-decoration: none; color: inherit;");
		content.href = linkGame;
		content.innerHTML = game;
	} else {
		content = document.createTextNode(game);		
	}
	th.setAttribute("style", "font-weight: bold; font-size: 120%;");	
	th.appendChild(content);
	th.colSpan = 2;
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	var th = document.createElement('TH');
	plays = document.createTextNode(play_count+" plays in "); // Play Count
	th.appendChild(plays);   

	var sessions = session_count + " sessions";
	var content;
	if (links == "CoGs") {
		content = document.createElement('a');
		content.setAttribute("style", "text-decoration: none; color: inherit;");
		content.href =  url_list_Sessions + "?rich&no_menus&index&game=" + pkg; 
		content.innerHTML = sessions;
	} else {
		content = document.createTextNode(sessions);
	}   
	th.appendChild(content);

	th.colSpan = 3;
	th.className = 'leaderboard normal'
		th.style.textAlign = 'center';
	tr.appendChild(th);
	
	// #############################################################
	// Second (optional) Header Row (session details if requested)

	var details = document.getElementById("chk_details").checked;
	
	if (details) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = "<div style='float: left; margin-right: 2ch; font-weight: bold;'>Results after:</div><div style='float: left;'>" + session_details_html + "</div>";
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	
	// If no details displayed at least display the date-time of the session
	// that produced this leaderboard snapshot
	} else {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var th = document.createElement('TH');
		var content = document.createTextNode("Results after " + date_time);
		th.appendChild(content);
		th.colSpan = 5;
		th.className = 'leaderboard normal'
		tr.appendChild(th);		
	}

	// #############################################################
	// Third Header Row

	var analysis_pre = document.getElementById("chk_analysis_pre").checked;

	if (analysis_pre) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = session_analysis_pre_html;
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	}

	// #############################################################
	// Fourth Header Row

	var analysis_post = document.getElementById("chk_analysis_post").checked;

	if (analysis_post) {
		let tr = document.createElement('TR');
		tableHead.appendChild(tr);

		let td = document.createElement('TD');
		td.innerHTML = session_analysis_post_html;
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	}

	// #############################################################
	// Fifth Header Row

	tr = document.createElement('TR');
	tableHead.appendChild(tr);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Rank"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	th = document.createElement('TH');
	th.appendChild(document.createTextNode("Player"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Teeth"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Plays"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Victories"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	// #############################################################
	// The Body

	const highlight_players = document.getElementById("chk_highlight_players").checked;
	const highlight_changes = document.getElementById("chk_highlight_changes").checked;
	const highlight_selected = document.getElementById("chk_highlight_selected").checked;
	
	const selected_players = options.players;  // A list of string ids

	const tableBody = document.createElement('TBODY');
	table.appendChild(tableBody);

	for (let i = 0; i < player_list.length; i++) {
		const tr = document.createElement('TR');
		tableBody.appendChild(tr);

		// Column Indices in player_list[i]:
		// 0 is the rank
		// 1 and 2 are the PK and BGGname,
		// 3, 4 and 5 are the nickname, full name and complete name of the
		// player respectively
		// 6, 7, and 8 are Trueskill eta, mu and sigma
		// 9 and 10 are play count and victory count
		const iRank = 0;
		const iPK = 1;
		const iBGGname = 2;
		const iNickName = 3;
		const iFullName = 4;
		const iCompleteName = 5;
		const iEta = 6;
		const iMu = 7;
		const iSigma = 8;
		const iPlays = 9;
		const iWins = 10;
		// 11 and 12 are last_play and player_leagues respectively not used here
		const iRankPrev = 13;   
		
		td_class = 'leaderboard normal';
		
		const this_player = player_list[i][iPK]; 
		
		// session_players is the list of players in the game session that
		// resulted in this leaderboard snapshot.
		if (session_players.indexOf(this_player) >= 0)
			td_class += highlight_players ? ' highlight_players_on' : ' highlight_players_off'; 

		// session_players is the list of players selected in the multiselect
		// player
		// selector box.
		if (selected_players.indexOf(this_player.toString()) >= 0)
			td_class += highlight_selected ? ' highlight_selected_on' : ' highlight_selected_off'; 

		// On all but the last snapshot we can render rank change highlights
		if (snapshot < last_snapshot) {
			const rank      = player_list[i][iRank];
			const prev_rank = player_list[i][iRankPrev];
			
			if (rank != prev_rank)
				td_class += highlight_changes ? ' highlight_changes_on' : ' highlight_changes_off';
		}

		const pkp = player_list[i][iPK];
		const BGGname = player_list[i][iBGGname];
		const rating  = player_list[i][iEta]
		const mu  = player_list[i][iMu]
		const sigma  = player_list[i][iSigma]
		const plays  = player_list[i][iPlays]
		const wins  = player_list[i][iWins]
		const play_count  = player_list[i][iPlays]
		const victory_count  = player_list[i][iWins]

		const linkPlayerCoGs = url_view_Player.replace('00',pkp);
		const linkPlayerBGG = BGGname ? "https:\/\/boardgamegeek.com/user/" + BGGname : null;
		const linkPlayer = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;
		
		// ###########################################################################
		// The RANK column
		const rank = player_list[i][iRank]
		
		const td_rank = document.createElement('TD');
		td_rank.style.textAlign = 'center';
		td_rank.className = td_class;
		td_rank.appendChild(document.createTextNode(rank));
		tr.appendChild(td_rank);

		// ###########################################################################
		// The PLAYER column
		const chosen_name = name_choice == 'nick' ? player_list[i][iNickName]
		                  : name_choice == 'full' ? player_list[i][iFullName]
			        	  : name_choice == 'complete' ? player_list[i][iCompleteName]
		                  : "ERROR";		
		
		const td_player = document.createElement('TD');
		td_player.className = td_class;
		
		if (linkPlayer) {
			const a_player = document.createElement('a');
			a_player.setAttribute("style", "text-decoration: none; color: inherit;");				
			a_player.href =  linkPlayer; 
			a_player.innerHTML = chosen_name;
			td_player.appendChild(a_player);
		} else {
			td_player.innerHTML = chosen_name;
		}

		tr.appendChild(td_player);

		// ###########################################################################
		// The TEETH/RATING column

		const fixed_rating = rating.toFixed(1);
		const fixed_mu = mu.toFixed(1);
		const fixed_sigma = sigma.toFixed(1);

		const td_rating = document.createElement('TD');
		td_rating.className = td_class;
		td_rating.style.textAlign = 'center'
		
		const div_rating = document.createElement('div');
		div_rating.setAttribute("class", "tooltip");
		div_rating.innerHTML = fixed_rating;
		
		const tt_rating = document.createElement('span');
		tt_rating.className = "tooltiptext";
		tt_rating.style.width='400%'
		tt_rating.innerHTML = "	&mu;=" + fixed_mu + " &sigma;=" + fixed_sigma; 
		
		div_rating.appendChild(tt_rating);
		td_rating.appendChild(div_rating);
		tr.appendChild(td_rating);		
		
		// ###########################################################################
		// The PLAY COUNT column
		
		const td_plays = document.createElement('TD');
		td_plays.className = td_class;
		td_plays.style.textAlign = 'center'
		
		const a_plays = document.createElement('a');
		a_plays.setAttribute("style", "text-decoration: none; color: inherit;");				
		a_plays.href =  url_list_Sessions + "?performances__player=" + pkp + "&game=" + pkg + "&detail&external_links&no_menus&index"; 
		a_plays.innerHTML = plays;

		td_plays.appendChild(a_plays);
		tr.appendChild(td_plays);
		
		// ###########################################################################
		// The WIN COUNT column
		
		const td_wins = document.createElement('TD');
		td_wins.className = td_class;
		td_wins.style.textAlign = 'center'
		
		// FIXME: What link can get victories in teams as well?
		// And are team victories listed in the victory count at all?
		// url_filters can only be ANDs I think, so this hard for team
		// victories. One way is if Performance has a field is_victory
		// that can be filtered on. Currently has a property that returns
		// this. Can url_filter filter on properties? Via Annotations on
		// a query?
		
		const a_wins = document.createElement('a');
		a_wins.setAttribute("style", "text-decoration: none; color: inherit;");				
		a_wins.href =  url_list_Sessions + "?ranks__rank=1&ranks__player=" + pkp + "&game=" + pkg + "&detail&external_links&no_menus&index";; 
		a_wins.innerHTML = wins;

		td_wins.appendChild(a_wins);
		tr.appendChild(td_wins);
	}
		
	return table;
}

// Draw all leaderboards, sending to target and enabling links or not
function DrawTables(target, links) {
	// Oddly the jQuery forms $('#links') and $('#cols') fails here. Not sure
	// why.
	const selLinks = document.getElementById("links");	
	const selCols = document.getElementById("cols");
	let cols = parseInt(selCols.options[selCols.selectedIndex].text);	

	if (links == undefined) links = selLinks.value == "none" ? null : selLinks.value;

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
					cell.className = 'leaderboard wrapper'
					cell.appendChild(LBtable(leaderboards[k], 0, links));
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
			snaps = leaderboards[lb][3].length;
			for (var j = 0; j < snaps; j++) {
				var cell = row.insertCell(j);
				cell.className = 'leaderboard wrapper'
				cell.appendChild(LBtable(leaderboards[lb], j, links));
			}
			lb++; 
		}			
	}			 
}

InitControls(options);
DrawTables("tblLB");

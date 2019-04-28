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

// We fetch new leaderboards via AJAX and so need to reappraise them when they arrive
function get_and_report_metrics(LB) {
	var snapshots = 0; 
	boardcount = LB.length;
	maxshots = 0;
	totalshots = 0;
	for (var g=0; g<boardcount; g++) {
		snapshots = LB[g][3].length;
		totalshots += snapshots;
		if (snapshots > maxshots) maxshots = snapshots;
	}	 

	lblTotalCount = document.getElementById("lblTotalCount");
	lblTotalCount.innerHTML = "<b>" +  boardcount + "</b> leaderboards"; 
	
	if (totalshots > boardcount) {
		lblSnapCount = document.getElementById("lblSnapCount");
		lblSnapCount.innerHTML = "(" + totalshots + " snapshots)";
	}
}

// But on first load we have leaderboards that were provided through context, so process those now 
get_and_report_metrics(leaderboards);

// An initialiser for Select2 widgets used. Alas not so trivial to set
// as descrribed here: 
//   https://select2.org/programmatic-control/add-select-clear-items#preselecting-options-in-an-remotely-sourced-ajax-select2
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
			// {"results": [{"id": "1", "text": "Bernd", "selected_text": "Bernd"}, {"id": "2", "text": "Blake", "selected_text": "Blake"}], "pagination": {"more": false}}
				
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

function InitControls(options) {
	// We'll follow the same order as Leaderboards.views.leaderboard_options
	// This takes those same options provided in context (or from an ajx call) 
	// as "options" and initialises the controls on the page. 
	
	// Start with the method selectors (radio button selection is little different in JQuery, to other widgets)
	$("input[name=game_selection][value="+options.game_selection+"]").prop('checked', true);
	$("input[name=evolution_selection][value="+options.evolution_selection+"]").prop('checked', true);

	// Then we populate all the Game selectors, starting with the three multiselectors
	// We request displaying of games only that are listed or played in the listed leagues 
	// or by the listed players. 
	Select2Init($('#games'), options.games)
	Select2Init($('#leagues'), options.leagues)
	Select2Init($('#players'), options.players)
		
	// Then the rest of the game selectors
	$('#changed_since').val(options.changed_since == defaults.changed_since ? '' : options.changed_since);
	$('#num_games').val(options.num_games);
	$('#num_days').val(options.num_days);	  // Mirror of num_days_ev
	$('#num_days_ev').val(options.num_days);  // Mirror of num_days

	// Then the player selectors
	$('#num_players').val(options.num_players);
	$('#num_players_context').val(options.num_players_context);
	$('#min_plays').val(options.min_plays);
	$('#played_since').val(options.played_since == defaults.played_since ? '' : options.played_since);
	
	// Then the snapshot selectors
	$('#as_at').val(options.as_at == defaults.as_at ? '' : options.as_at);
	$('#compare_with').val(options.compare_with);
	$('#compare_back_to').val(options.compare_back_to == defaults.compare_back_to ? '' : options.compare_back_to);
	
	// Then the extra info options for leaderboard headers
	$('#chkSessionDetails').prop('checked', options.details.boolean());
	$('#chkSessionAnalysisPre').prop('checked', options.analysis_pre.boolean());
	$('#chkSessionAnalysisPost').prop('checked', options.analysis_post.boolean());

	// The the content formatting options
	$('#chkHighlightPlayers').prop('checked', options.highlight_players.boolean())
	$('#chkHighlightChanges').prop('checked', options.highlight_changes.boolean())
	
	$('#names').val(options.names);	
	$('#links').val(options.links);

	// Then the leaderboard screen layout options
	$('#cols').val(options.cols);
	
	//Configure the Copy Button
	const copybutton = document.getElementById("btnCopy");
	const clipboard = new ClipboardJS(copybutton);
	
	//What to do when the copy button is clicked 
	clipboard.on('success', function(e) {
		const copy_div = document.getElementById('tblLB_naked');
		e.clearSelection();
		copy_div.parentNode.removeChild(copy_div);
	});	
}

function URLopts(element) {
	// The opposite so to speal of InitControls() here we read those same conrols and prepare
	// URL options for self same to submit an AJAX request for updates (or simply display on
	// the address bar if desired)
	//
	// Again we'll follow the same order as in InitControls and Leaderboards.views.leaderboard_options
	// but in the URL we will only include values that deviate form the defaults (in the interests of
	// brevity and efficiency. Also, the broader game and evolution only submitting options relevant 
	// to that option (again, for brevity and efficiency)
	
	// Start with the method selectors (radio button selection is little different in JQuery, to other widgets)
	const game_selection = $("input[name='game_selection']:checked").val();
	const evolution_selection = $("input[name='evolution_selection']:checked").val();
	
	// Then get the values of the trhee multiselect game specifierd
	const leagues = $('#leagues').val().join(",");
	const games = $('#games').val().join(",");
	const players = $('#players').val().join(",");
	
	// Then the rest of the game selectors
	const changed_since = $('#changed_since').val();
	const num_games = $('#num_games').val();
	const num_days = $('#num_days').val();
	
	// Then the player selectors
	const num_players = $('#num_players').val();
	const num_players_context = $('#num_players_context').val();
	const min_plays = $('#min_plays').val();
	const played_since = $('#played_since').val();
	
	// Then the snapshot selectors
	const as_at = $('#as_at').val();
	const compare_with = $('#compare_with').val();
	const compare_back_to = $('#compare_back_to').val();
	
	// Then the extra info options for leaderboard headers
	const details = $('#chkSessionDetails').is(":checked");
	const analysis_pre = $('#chkSessionAnalysisPre').is(":checked");
	const analysis_post = $('#chkSessionAnalysisPost').is(":checked");
	
	// The the content formatting options
	const highlight_players = $('#chkHighlightPlayers').is(":checked");
	const highlight_changes = $('#chkHighlightChanges').is(":checked");
	
	const names = $('#names').val();	
	const links = $('#links').val();

	// Then the leaderboard screen layout options
	const cols = $('#cols').val();
	
	// Now push the Game selectors selectively onto opts
	let opts = [];

	// League filtering on games is always an overlay on the rest of the game selectors
	opts.push("leagues="+encodeURIComponent(leagues).replace(/%2C/g, ","))
	
	// Push even default values as the existence of the value also flags 
	// the game_selection implicitly, so we don't need to push its value.
	// But don't push empty values, they have no meaning. 
	switch(game_selection) {
	  case "selected":
		  	if (games)
		  		opts.push("games="+encodeURIComponent(games).replace(/%2C/g, ","))
		    break;
	  case "top_n":
		  	if (num_games)
		  		opts.push("num_games="+encodeURIComponent(num_games))
		    break;
	  case "activity":
		  	if (changed_since)
		  		opts.push("changed_since="+encodeURIComponent(changed_since))
		    break;
	  case "played_by":
		  	if (players)
		  		opts.push("players="+encodeURIComponent(players).replace(/%2C/g, ","))
		    break;
	  case "session_impact":
		  	if (num_days)
		  		opts.push("num_days="+encodeURIComponent(num_days))
		    break;
	}		

	// Push the player selectors only if they are not default values or null values
	if (num_players && num_players != defaults.num_players) opts.push("num_players="+encodeURIComponent(num_players))
	if (num_players_context && num_players_context != defaults.num_players_context) opts.push("num_players_context="+encodeURIComponent(num_players_context))
	if (min_plays && min_plays != defaults.min_plays) opts.push("min_plays="+encodeURIComponent(min_plays))
	if (played_since && played_since != defaults.played_since) opts.push("played_since="+encodeURIComponent(played_since))

	// Now push the snapshot selectors
	if (as_at && as_at != defaults.as_at) opts.push("as_at="+encodeURIComponent(as_at))
	
	// The evolution_selection can also be implied by submission of one of the three
	// key values. Note that the num_days are a mirrored box to the game_selector
	// but we can gave these sensible combinations:
	//
	// select_game on session and evolution on session
	// select_game on session and evolution some other way
	// select game some other way and evolution on session
	//
	// The last one is special as each game would have it's own last n day session!
	//
	// Method in use: flag with special value of compare_back_to coded as 
	// n_day_impact.
	switch(evolution_selection) {
	  case "n_prior":
		  	if (compare_with)
		  		opts.push("compare_with="+encodeURIComponent(compare_with));
			break;
	  case "back_to":
		  	if (compare_back_to && compare_back_to != defaults.compare_back_to)
		  		opts.push("compare_back_to="+encodeURIComponent(compare_back_to));
		    break;
	  case "session_impact":
		  	if (num_days)
		  		opts.push("compare_back_to=" + encodeURIComponent(num_days) + "_day_impact");
		    break;
	}

	// Then the extra info options for leaderboard headers
	if (details != defaults.details.boolean()) opts.push("details="+encodeURIComponent(details));
	if (analysis_pre != defaults.analysis_pre.boolean()) opts.push("analysis_pre="+encodeURIComponent(analysis_pre));
	if (analysis_post != defaults.details.boolean()) opts.push("analysis_post="+encodeURIComponent(analysis_post));

	// The the content formatting options
	if (highlight_players != defaults.highlight_players.boolean()) opts.push("highlight_players="+encodeURIComponent(highlight_players));
	if (highlight_changes != defaults.highlight_changes.boolean()) opts.push("highlight_changes="+encodeURIComponent(highlight_changes));
	
	if (names != defaults.names) opts.push("names="+encodeURIComponent(names));
	if (links != defaults.links) opts.push("links="+encodeURIComponent(links));
	
	// Then the leaderboard screen layout options
	if (cols != defaults.cols) opts.push("cols="+encodeURIComponent(cols));
	
	// Join the opts and return them 
	return (opts.length > 0) ? "?" + opts.join("&") : "";
}

function LabelButton(element) {
	var opts = []
	
	val = $('#selPlayer :selected').text(); if (val != $('#selPlayer option:first').text()) opts.push(val);	
	val = $('#selLeague :selected').text(); if (val != $('#selLeague option:first').text()) opts.push("the " + val + " league");
	
	qual = " for " + opts.join(" in ");
	label = "All Leaderboards" + (opts.length > 0 ? qual : "");
	
	$('#'+element).val(label);
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
function check_check(me, boxes) { $(boxes).prop('checked', Boolean(me.value)); }
function check_radio(me, name, value, fallback) { $("input[name='"+name+"'][value='"+(me.value?value:fallback)+"']").prop("checked",true); }
function only_one(me, others) {	if (me.checked)	$(others).prop('checked', false); }
function mirror(me, to) { $(to).val(me.value); }
function copy_if_empty(me, to) { if ($(to).val() == '') $(to).val(me.value); }
function blank_zero(me) { if (me.value == 0) me.value = ""; }
function show_url() { window.history.pushState("","", url_leaderboards.replace(/\/$/, "") + URLopts(null)); }

var REQUEST = new XMLHttpRequest();
REQUEST.onreadystatechange = function () {
	if (this.readyState === 4 && this.status === 200){
		// the request is complete, parse data 
		var response = JSON.parse(this.responseText);

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
		
		$("#reloading_icon").css("visibility", "hidden");		
	}
};

function refetchLeaderboards(event) {
	var url = url_json_leaderboards + URLopts(event.target.id);

	$("#reloading_icon").css("visibility", "visible");

	REQUEST.open("GET", url, true);
	REQUEST.send(null);
}

function prepare_target()  {
	const copy_table = document.createElement('TABLE');
	copy_table.id = "tblLB_naked";

	const copy_div = document.createElement('DIV');
	copy_div.id = 'divLB_naked'
	copy_div.style.position = 'absolute';
	copy_div.style.left = '-99999px';
	
	// Alas the Div gets swallowed by the clipboards code somehow, 
	// as does any div I wrap the table in. Meaning I can't find a way 
	// to copy with an overflow:auto div. I spent ages experimenting with 
	// no success,
	
	// Some tests:
	// Chromium: Just copies the table
	// Firefox: copies the div
	// Arora: copies nothing (low end browser)
	// Web: copies only the table
	
	copy_div.appendChild(copy_table);		// Put the table in the wrapping div
	document.body.appendChild(copy_div);	// Put the copy div into the document
	
	DrawTables(copy_table.id, "BGG");
}

//Function to draw one leaderboard table
function LBtable(LB, snapshot, links) {
//	A list of lists which have four values: Game PK, Game BGGid, Game name, Snapshots
//	Snapshots is a list of lists which have five values: Date time string, count of plays, count of sessions, session details and Leaderboard
//	Leaderboard is a list of lists which have six values: Player PK, Player BGGid, Player name, Trueskill rating, Play count, Victory count

	// Extract the data we need
	var pkg = LB[0];
	var BGGid = LB[1];
	var game = LB[2];

	// This MUST align with the way ajax_Leaderboards() bundles up leaderboards
	// Rather a complex structure that may benefit from some naming (rather than
	// being a list of lists of lists of lists look at named object properties.
	var date_time = LB[3][snapshot][0]
	var play_count = LB[3][snapshot][1];
	var session_count =LB[3][snapshot][2];
	var session_players = LB[3][snapshot][3];
	var session_details_html = LB[3][snapshot][4][0];
	var session_details_data = LB[3][snapshot][4][1];
	var session_analysis_pre_html = LB[3][snapshot][5][0];
	var session_analysis_pre_data = LB[3][snapshot][5][1];
	var session_analysis_post_html = LB[3][snapshot][6][0];
	var session_analysis_post_data = LB[3][snapshot][6][1];
	var player_list = LB[3][snapshot][7];
	var player_prev = (snapshot+1<LB[3].length) ? LB[3][snapshot+1][7] : null; 

	
	// Create the Game link based on the requested link target
	var linkGameCoGs = url_view_Game.replace('00',pkg);
	var linkGameBGG = "https:\/\/boardgamegeek.com/boardgame/" + BGGid;
	var linkGame = links == "CoGs" ? linkGameCoGs : links == "BGG" ?  linkGameBGG : null;

	// Fix the session detail and analysis headers which were provided with templated links
	var linkPlayerCoGs = url_view_Player.replace('00','{ID}');
	var linkPlayerBGG = "https:\/\/boardgamegeek.com/user/{ID}";
	var linkTeamCoGs = url_view_Team.replace('00','{ID}');
	
	var linkRanker = {};
	linkRanker["Player"] = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;
	linkRanker["Team"] = links == "CoGs" ? linkTeamCoGs : links == "BGG" ?  null : null;

	// Build a map of PK to BGGid for all rankers
	// Note, session_details_data, session_analysis_pre_data and session_analysis_post_data perforce
	// contain the same map (albeit in a different order) so we can use just one of them to build the map. 
	var linkRankerID = {}
	for (var r = 0; r < session_details_data.length; r++) {
		var PK = session_details_data[r][0];
		var BGGname = session_details_data[r][1];
		
		linkRankerID[PK] = links == "CoGs" ? PK : links == "BGG" ?  BGGname : null;
	}

	// A regex replacer which has as args first the matched string then each of the matched subgroups
	// The subgroups we expect for a leaderboard header template is klass, model, id and then the text.
	// This is a function that the following replace() functions pass matched groups to and is tasked
	// with returning a the replacement string. 
	function fix_template_link(match, klass, model, id, txt) {
		if (linkRankerID[id] == null) 
			return txt;
		else {
			var url = linkRanker[model].replace('{ID}', linkRankerID[id]);
			return "<A href='"+url+"' class='"+klass+"'>"+txt+"</A>";
		}
	}
	
	// Fix the HTML of the headers
	session_details_html = session_details_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	session_analysis_pre_html = session_analysis_pre_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	session_analysis_post_html = session_analysis_post_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	
	var table = document.createElement('TABLE');
	table.className = 'leaderboard'
	table.style.width = '100%';

	// Five header rows as follows:
	// A full-width session detail block, or the date the leaderboard was set (of last session played that contributed to it)
	// A full-width pre session analysis
	// A full-width post session analysis
	// A game header with the name of the game (2 cols) and play/session summary (3 cols)
	// A final header with 5 column headers (rank, player, rating, plays, victories)

	var tableHead = document.createElement('THEAD');
	table.appendChild(tableHead);	    

	// First Header Row

	var tr = document.createElement('TR');
	tableHead.appendChild(tr);

	var th = document.createElement('TH');
	var content;
	if (linkGame) {
		content = document.createElement('a');
		content.setAttribute("style", "text-decoration: none; color: inherit; font-weight: bold; font-size: 120%;");
		content.href = linkGame;
		content.innerHTML = game;
	} else {
		content = document.createTextNode(game);
	}   
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
		content.href =  url_list_Sessions + "?game=" + pkg; 
		content.innerHTML = sessions;
	} else {
		content = document.createTextNode(sessions);
	}   
	th.appendChild(content);

	th.colSpan = 3;
	th.className = 'leaderboard normal'
		th.style.textAlign = 'center';
	tr.appendChild(th);
	
	// Second (optional) Header Row (session details if requested)

	var details = document.getElementById("chkSessionDetails").checked;
	
	if (details) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = "<div style='float: left; margin-right: 2ch; font-weight: bold;'>Results after:</div><div style='float: left;'>" + session_details_html + "</div>";
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	
	// If no details displayed at least display the date-time of the session that produced this leaderboard snapshot
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

	// Third Header Row

	var analysis_pre = document.getElementById("chkSessionAnalysisPre").checked;

	if (analysis_pre) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = session_analysis_pre_html;
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	}

	// Fourth Header Row

	var analysis_post = document.getElementById("chkSessionAnalysisPost").checked;

	if (analysis_post) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = session_analysis_post_html;
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
	}

	// Fifth Header Row

	var tr = document.createElement('TR');
	tableHead.appendChild(tr);

	var th = document.createElement('TH');
	th.appendChild(document.createTextNode("Rank"));
	th.className = 'leaderboard normal'
		tr.appendChild(th);

	var th = document.createElement('TH');
	th.appendChild(document.createTextNode("Player"));
	th.className = 'leaderboard normal'
		tr.appendChild(th);

	var th = document.createElement('TH');
	th.appendChild(document.createTextNode("Teeth"));
	th.className = 'leaderboard normal'
		tr.appendChild(th);

	var th = document.createElement('TH');
	th.appendChild(document.createTextNode("Plays"));
	th.className = 'leaderboard normal'
		tr.appendChild(th);

	var th = document.createElement('TH');
	th.appendChild(document.createTextNode("Victories"));
	th.className = 'leaderboard normal'
		tr.appendChild(th);

	// Body

	const highlight_players = document.getElementById("chkHighlightPlayers").checked;
	const highlight_changes = document.getElementById("chkHighlightChanges").checked;
	const highlight_selected = document.getElementById("chkHighlightSelected").checked;
	
	const selected_players = options.players;  // A list of string ids

	const tableBody = document.createElement('TBODY');
	table.appendChild(tableBody);

	for (let i = 0; i < player_list.length; i++) {
		const tr = document.createElement('TR');
		tableBody.appendChild(tr);

		td_class = 'leaderboard normal';
		const this_player = i<player_list.length ? player_list[i][0] : null; 
		
		if (session_players.indexOf(this_player) >= 0)
			td_class += highlight_players ? ' highlight_players_on' : ' highlight_players_off'; 

		if (selected_players.indexOf(this_player.toString()) >= 0)
			td_class += highlight_selected ? ' highlight_selected_on' : ' highlight_selected_off'; 

		if (player_prev) {
			var prev_player = i<player_prev.length ? player_prev[i][0] : null;
			if (this_player != prev_player)
				td_class += highlight_changes ? ' highlight_changes_on' : ' highlight_changes_off';
		}

		// The Rank column
		var td = document.createElement('TD');
		td.style.textAlign = 'center';
		td.className = td_class;
		td.appendChild(document.createTextNode(i+1));  // Rank
		tr.appendChild(td);

		// The remaining columns
		// 0 and 1 are the PK and BGGname, 2 to 5 are the leaderboard data
		for (var j = 2; j < 6; j++) {
			var td = document.createElement('TD');
			td.className = td_class;

			var pkp = player_list[i][0];
			var BGGname = player_list[i][1];

			var linkPlayerCoGs = url_view_Player.replace('00',pkp);
			var linkPlayerBGG = BGGname ? "https:\/\/boardgamegeek.com/user/" + BGGname : null;
			var linkPlayer = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;

			var val = player_list[i][j]

			if (j==3) { val = val.toFixed(1) }				// Teeth
			if (j!=2) { td.style.textAlign = 'center'; }	// ! Player

			// Add Links
			var content;
			if ((linkPlayer && j==2) || (links == "CoGs" && (j==4 || j==5))) {
				content = document.createElement('a');
				content.setAttribute("style", "text-decoration: none; color: inherit;");
				if (j==2) {   // Player Name
					content.href =  linkPlayer; 
				} else if (j==4) { // Play Count
					content.href =  url_list_Sessions + "?performances__player=" + pkp + "&game=" + pkg + "&detail&external_links&no_menus&index";  
				} else if (j==5) { // Victory Count
					// FIXME: What link can get victories in teams as well?
					//        And are team victories listed in the victory count at all?
					//        url_filters can only be ANDs I think, so this hard for team
					//        victories. One way is if Performance has a field is_victory
					//        that can be filtered on. Currently has a property that returns this
					content.href =  url_list_Sessions + "?ranks__rank=1&ranks__player=" + pkp + "&game=" + pkg + "&detail&external_links&no_menus&index";;  
				}
				content.innerHTML = val;
			} else {
				content = document.createElement('span');  // Need a span to make it bold on a player filter match
				var text = document.createTextNode(val);
				content.appendChild(text); 
			}

			if (j==2 && pkp==options.player) {
				content.style.fontWeight = 'bold';
			}

			td.appendChild(content);
			tr.appendChild(td);
		}
	}
	return table;
}

//Draw all leaderboards, sending to target and enabling links or not
function DrawTables(target, links) {
	// Oddly the jQuery forms $('#links') and $('#cols') fails here. Not sure why. 
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
//  This was a clever way to to support pairs that run across the screen.
//  Have decided in interim that we won't support that. It's much nicer even with pairs
//  to run them one pair per row.
//	else if (maxshots == 2) {
//		// if cols is odd, add one so that comparisons are always side by side. So cols = 1 becomes 2 
//		// in the extreme.
//		if ( cols % 2 ) cols += 1;
//
//		// Now halve the number of columns as we're spiting out two tables at a time.
//		cols /= 2;   
//
//		// And base layout calcs on the total number of boards (so twice those presented, we'll
//		// leave gaps for any that don't have a comparison table.  
//		var totalboards = 2*leaderboards.length;
//
//		// Now very similar to case of maxshots==1, just in pairs.
//		var rows = totalboards / ( 2 * cols );
//		var remainder = totalboards - rows*cols;
//		if (remainder > 0) { rows++; }
//
//		// A wrapper table for the leaderboards 
//		var table = document.getElementById(target); 
//		table.innerHTML = "";
//		table.className = 'leaderboard wrapper'
//
//		var lb = 0; 
//		for (var i = 0; i < rows; i++) {
//			var row = table.insertRow(i);
//			for (var j = 0; j < cols; j++) {
//				if (lb < leaderboards.length) {
//					var cell1 = row.insertCell(2*j);
//					cell1.className = 'leaderboard wrapper'
//						cell1.appendChild(LBtable(leaderboards[lb], 0, links));
//
//					var cell2 = row.insertCell(2*j+1);
//					cell2.className = 'leaderboard wrapper'
//						if (leaderboards[lb][3].length > 1)		
//							cell2.appendChild(LBtable(leaderboards[lb], 1, links));
//						else
//							cell2.appendChild(document.createTextNode("No prior board for " + leaderboards[lb][2]));												
//				}
//				lb++; 
//			}
//		}
//	}
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

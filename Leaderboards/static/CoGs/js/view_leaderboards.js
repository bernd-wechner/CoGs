//Report the snapshot count
if (totalshots > leaderboards.length) {
	lblSnaps = document.getElementById("lblSnaps");
	lblSnaps.innerHTML = "(" + totalshots + " snapshots)";
}

function InitControls() {
	//Select the request cols
	selCols = $('#selCols');
	selCols.val(value_cols);
	
	//Select the request name style
	selNames = $('#selNames');
	selNames.val(value_names);
	
	//Select the request link style
	selLinks = $('#selLinks');
	selLinks.val(value_links);
	
	//Set the requested highlight
	var chkHighlightChanges = document.getElementById("chkHighlightChanges");
	chkHighlightChanges.checked = value_highlight;

	//Set the requested detail
	var chkSessionDetails = document.getElementById("chkSessionDetails");
	chkSessionDetails.checked = value_details;
	
	//Attach the datetimepicker to all DateTimeFields. Assumes DateTimeField widgets have the class "DateTimeField"
	var datetime_format = value_date_format;
	
	$(function(){
		$(".DateTimeField").datetimepicker({
			"format": datetime_format,
			"step" : 15
		});
	});
	
	//Populate the League selector
	var select = $('#selLeague');                        
	select.find('option').remove();    
	var league_choices = "";
	for (var i = 0, len = leagues.length; i < len; i++) {
		pair = leagues[i];
		league_choices += '<option value=' + pair[0] + (pair[0] == league ? ' selected ' : '') + '>' + pair[1] + '</option>';
	}	
	select.append(league_choices);
	
	//Populate the Player selector
	var select = $('#selPlayer');                        
	select.find('option').remove();    
	var player_choices = "";
	for (var i = 0, len = players.length; i < len; i++) {
		pair = players[i];
		player_choices += '<option value=' + pair[0] + (pair[0] == player ? ' selected ' : '') + '>' + pair[1] + '</option>';
	}	
	select.append(player_choices);
	
	//Populate the Game selector
	var select = $('#selGame');                        
	select.find('option').remove();    
	var game_choices = "";
	for (var i = 0, len = games.length; i < len; i++) {
		pair = games[i];
		game_choices += '<option value=' + pair[0] + (pair[0] == game ? ' selected ' : '') + '>' + pair[1] + '</option>';
	}	
	select.append(game_choices);
	
	//Configure the Copy Button
	var copybutton = document.getElementById("btnCopy");
	var clipboard = new Clipboard(copybutton);

	clipboard.on('success', function(e) {
		e.clearSelection();
		var clipboard_target = document.getElementById("divLB_naked");
		document.body.removeChild(clipboard_target);
	});	
}

function toggle_filters() {
	current = $(".toggle")[0].style.display;
	if (current == "none")
		$(".toggle").css('display', 'table-row');
	else
		$(".toggle").css('display', 'none');		
}

function toggle_highlights() {
	if (document.getElementById("chkHighlightChanges").checked)
		$(".leaderboard.highlight_off").removeClass().addClass('leaderboard highlight_on');
	else
		$(".leaderboard.highlight_on").removeClass().addClass('leaderboard highlight_off');
}

function copy_if_empty(from, to) {
	if ($(to).val() == '') $(to).val($(from).val());
}

function URLopts() {
	opts = []

	// Get the page elements		
	var selLeague = document.getElementById("selLeague");
	var selPlayer = document.getElementById("selPlayer");
	var selGame = document.getElementById("selGame");

	var from_date_time = document.getElementById("from_date_time");
	var as_at_date_time = document.getElementById("as_at_date_time");
	var compare_till_date_time = document.getElementById("compare_till_date_time");
	var compare_back_to_date_time = document.getElementById("compare_back_to_date_time");
	var compare_with = document.getElementById("compare_with");
	var chkHighlightChanges = document.getElementById("chkHighlightChanges");
	var chkSessionDetails = document.getElementById("chkSessionDetails");

	var selCols = $("#selCols");
	var selNames = $("#selNames");
	var selLinks = $("#selLinks");

	// Check their values
	if (selLeague.value != ALL_LEAGUES) opts.push("league="+selLeague.value);	
	if (selPlayer.value != ALL_PLAYERS) opts.push("player="+selPlayer.value);	
	if (selGame.value != ALL_GAMES) opts.push("game="+selGame.value);	

	if (from_date_time.value != "") opts.push("changed_since="+encodeURIComponent(from_date_time.value));
	if (as_at_date_time.value != "") opts.push("as_at="+encodeURIComponent(as_at_date_time.value));
	if (compare_till_date_time.value != "") opts.push("compare_till="+encodeURIComponent(compare_till_date_time.value));
	if (compare_back_to_date_time.value != "") opts.push("compare_back_to="+encodeURIComponent(compare_back_to_date_time.value));
	if (compare_with.value != "" && compare_with.value != 0) opts.push("compare_with="+encodeURIComponent(compare_with.value));
	if (chkHighlightChanges.checked != Boolean(default_highlight)) opts.push("highlight="+encodeURIComponent(chkHighlightChanges.checked));
	if (chkSessionDetails.checked != Boolean(default_details)) opts.push("details="+encodeURIComponent(chkSessionDetails.checked));

	if (selCols.val() != default_cols) opts.push("cols="+selCols.val());
	if (selNames.val() != default_names) opts.push("names="+selNames.val());	
	if (selLinks.val() != default_links) opts.push("links="+selLinks.val());

	return (opts.length > 0) ? "?" + opts.join("&") : "";
}

function get_new_view() {
	var url = url_leaderboards + URLopts();
	window.location.href = url;
}

function refetchLeaderboards(event) {
	var url = url_json_leaderboards + URLopts();

	var REQUEST = new XMLHttpRequest();

	REQUEST.onreadystatechange = function () {
		if (this.readyState === 4 && this.status === 200){
			// the request is complete, parse data 
			var response = JSON.parse(this.responseText);

			// Capture response in leaderboards
			leaderboards = response;

			// redraw the leaderboards
			DrawTables("tblLB");
		}
	};

	REQUEST.open("GET", url, true);
	REQUEST.send(null);
}

function prepare_target()  {
	var copy_table = document.createElement('TABLE');
	copy_table.id = "tblLB_naked";

	var copy_div = document.createElement('DIV');
	copy_div.id = 'divLB_naked'
	copy_div.style.position = 'absolute';
	copy_div.style.left = '-99999px';
	
	// Alas the Div gets swallowed by the clipboards code somewhow, 
	// as does any div I wrap the table in. Meaning I can't find a way 
	// to copy with an overflow:auto div. I spemt ages experimenting with 
	// no success,
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

	var date_time = LB[3][snapshot][0]
	var play_count = LB[3][snapshot][1];
	var session_count =LB[3][snapshot][2];
	var session_details_html = LB[3][snapshot][3][0];
	var session_details_data = LB[3][snapshot][3][1];
	var player_list = LB[3][snapshot][4];

	// Note the previous snapshots player list if there is one
	// for the purposes of highlighting changes.   
	var player_prev = null;
	if (snapshot+1<LB[3].length) {
		player_prev = LB[3][snapshot+1][4];	
	}

	// Create the Game link based on the requested link target
	var linkGameCoGs = url_view_Game.replace('00',pkg);
	var linkGameBGG = "https:\/\/boardgamegeek.com/boardgame/" + BGGid;
	var linkGame = links == "CoGs" ? linkGameCoGs : links == "BGG" ?  linkGameBGG : null;

	// Fix the session detail header which was provided with templated links
	var linkPlayerCoGs = url_view_Player.replace('00','{ID}');
	var linkPlayerBGG = "https:\/\/boardgamegeek.com/user/{ID}";
	var linkTeamCoGs = url_view_Team.replace('00','{ID}');
	
	var linkRanker = {};
	linkRanker["Player"] = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;
	linkRanker["Team"] = links == "CoGs" ? linkTeamCoGs : links == "BGG" ?  null : null;

	var linkRankerID = {}
	for (var r = 0; r < session_details_data.length; r++) {
		var PK = session_details_data[r][0];
		var BGGname = session_details_data[r][1];
		
		linkRankerID[PK] = links == "CoGs" ? PK : links == "BGG" ?  BGGname : null;
	}

	function fix_session_detail_link(match, klass, model, id, txt) {
		if (linkRankerID[id] == null) 
			return txt;
		else {
			var url = linkRanker[model].replace('{ID}', linkRankerID[id]);
			return "<A href='"+url+"' class='"+klass+"'>"+txt+"</A>";
		}
	}
	
	if (links == "CoGs" || links == "BGG" )
		session_details_html = session_details_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_session_detail_link);
	
	var table = document.createElement('TABLE');
	table.className = 'leaderboard'
	table.style.width = '100%';

	// Three header rows as folows:
	// One fullwidth containing the date the leaderboard was set (of lasts ession played that contributed to it)
	// A second with the game name (2 cols) and play/session summary (3 cols)
	// A third with 5 column headers (rank, player, rating, plays, victories)

	var tableHead = document.createElement('THEAD');
	table.appendChild(tableHead);	    

	// First Header Row

	var details = document.getElementById("chkSessionDetails").checked;
	
	if (details) {
		var tr = document.createElement('TR');
		tableHead.appendChild(tr);

		var td = document.createElement('TD');
		td.innerHTML = "<div style='float: left; margin-right: 2ch;'><b>Results after:</b></div><div style='float: left;'>" + session_details_html + "</div>";
		td.colSpan = 5;
		td.className = 'leaderboard normal'
		tr.appendChild(td);
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

	// Second Header Row

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

	// Third Header Row

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

	var highlight = document.getElementById("chkHighlightChanges").checked ? 'leaderboard highlight_on' : 'leaderboard highlight_off';

	var tableBody = document.createElement('TBODY');
	table.appendChild(tableBody);

	for (var i = 0; i < player_list.length; i++) {
		var tr = document.createElement('TR');
		tableBody.appendChild(tr);

		td_class = 'leaderboard normal';
		if (player_prev) {
			var this_player = i<player_list.length ? player_list[i][0] : null; 
			var prev_player = i<player_prev.length ? player_prev[i][0] : null;
			if (this_player != prev_player)
				td_class = highlight; 
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
					content.href =  url_list_Sessions + "?performances__player=" + pkp + "&game=" + pkg;  
				} else if (j==5) { // Victory Count
					// FIXME: What link can get victories in teams as well?
					//        And are team victories listed in the victory count at all?
					//        url_filters can only be ANDs I think, so this hard for team
					//        victories. One way is if Performance has a field is_victory
					//        that can be filtered on. Currently has a property that returns this
					content.href =  url_list_Sessions + "?ranks__rank=1&ranks__player=" + pkp + "&game=" + pkg;  
				}
				content.innerHTML = val;
			} else {
				content = document.createElement('span');  // Need a span to make it bold on a player filter match
				var text = document.createTextNode(val);
				content.appendChild(text); 
			}

			if (j==2 && pkp==player) {
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
	// Oddly $('#selLinks) and $('#selCols) fails here. Not sure why. 
	var selLinks = document.getElementById("selLinks");
	var selCols = document.getElementById("selCols");
	var cols = parseInt(selCols.options[selCols.selectedIndex].text);

	// TODO: We need to respect links in the new detail header!
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

InitControls();
DrawTables("tblLB");

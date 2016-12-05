debug = false;

// Attach a datetimepicker to all DateTimeFields. Assumes DatimeField widgets have the class "DateTimeField"
$(function(){
	$(".DateTimeField").datetimepicker({
		"format": datetime_format,
		"step" : 15
	});
});

var id_prefix   =	 "id_";				// This is the prefix to element ID strings Django formsets use. A form element has "id=id_yadayada name=yadayada" properties
var form_number = '__prefix__';			// This should be replaced by the number of the form, 0, 1, 2, 3 and so on for each form in the formset

// Specify the related model prefixes used in field names
var rank_prefix 		= "Rank-"
var performance_prefix 	= "Performance-"
var team_prefix 		= "Team-"

// Define some widget names. form_number will be replaced by the form number when new ones are created.
// 		On edit, we need to put the IDs of the Rank and Performance objects on the form so that on save we know which ones to save.
// 		We don't need to do this for Team objects as Teams are defined by their members, i.e the Player IDs and these are stored in the Player field itself.
var name_rid     		  = rank_prefix + form_number + '-id';                        // The Ranking ID in the database (ranks are stored in a model of their own, called Rank)
var name_pid     		  = performance_prefix + form_number + '-id';                 // The Performance ID in the database (partial play weights are stored in a model of their own called Performance)

//The Django management form fields we need to keep up to date reflecting the number of forms in the formset if we want Django to save them for us
var name_rinit     	  	  = rank_prefix + "INITIAL_FORMS";
var name_pinit     	      = performance_prefix + 'INITIAL_FORMS';
var name_rtotal     	  = rank_prefix + "TOTAL_FORMS";
var name_ptotal     	  = performance_prefix + 'TOTAL_FORMS';

// Actual model fields
var name_rank   		  = rank_prefix + form_number + '-rank';						 	// Ranking (1st, 2nd, 3rd)
var name_player     	  = performance_prefix + form_number + '-player';	                // Player name/id in the Performance object (and the the selector)
var name_player_copy   	  = rank_prefix + form_number + '-player';	                        // Player name/id in the Rank object in individual play mode (copied from name_player on submit)
var name_weight 		  = performance_prefix + form_number + '-partial_play_weighting'; 	// Partial play weighting (0-1)

var name_team_name  	  = team_prefix + form_number + '-name';
var name_num_team_players = team_prefix + form_number + '-num_players';

// Define the IDs of some vital control elements for the smooth operation of the form.
var id_num_players		  = "NumPlayers";												// ID of the field that contains the number of players (in in Individual Play mode)
var id_num_teams		  = "NumTeams";													// ID of the field that contains the number of teams (in in Team Play mode)

var id_tbl_players 		  = "tblPlayersTable";											// ID of the table that contains the players (in in Individual Play mode)
var id_tbl_teams 		  = "tblTeamsTable";											// ID of the table that contains the teams (in in Team Play mode)

var id_team_switch 	 	  = id_prefix + 'team_play';								 	// The checkbox used to switch between Individual play mode and Team play mode

// Add event listeners to initialize the form and to tidy it on submit
window.addEventListener('load', OnLoad, true);
window.addEventListener('submit', OnSubmit, true);

function OnLoad(event) {
	var team_switch = $$(id_team_switch);
	team_switch.addEventListener('click', switchMode)
	
	var game_selector = $$(id_prefix+"game");
	game_selector.addEventListener('change', switchGame)
	
	// If Teams are specified on loading we are in Team Play mode by default with all the defaults specified.
	if (Teams.length > 0) {
		$$('divIndividualPlay').style.display = 'none';
		$$('divTeamPlay').style.display = 'block';

		// Constrain the supplied data to expected bounds 
		if (Teams.length < game_min_players/game_max_players_per_team) Teams.length = game_min_players/game_max_players_per_team;  
		if (Teams.length > game_max_players/game_min_players_per_team) Teams.length = game_max_players/game_min_players_per_team; 
		$$(id_num_teams).value = Teams.length;

		adjustTable($$(id_num_teams));

		// For each team build the Team players table
		for (var i = 0; i < $$(id_num_teams).value; i++) {
			var numPlayers = TeamPlayers[i].length;
			if (numPlayers < game_min_players_per_team) numPlayers = game_min_players_per_team;  
			if (numPlayers > game_max_players_per_team) numPlayers = game_max_players_per_team; 

			if (numPlayers > 0) {
		    	var idTable = 'tblTeamsBody' + i;
		    	var Table = $$(idTable);
	            var boxNum = findChildByName(Table, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.

                boxNum.value = numPlayers;

                adjustTable(boxNum);
            }
        }
	} else {
		$$('divIndividualPlay').style.display = 'block';
		$$('divTeamPlay').style.display = 'none';

		// Constrain the supplied data to expected bounds 
		if (Players.length < game_min_players) Players.length = game_min_players;  
		if (Players.length > game_max_players) Players.length = game_max_players; 
    	$$(id_num_players).value = Players.length;

        adjustTable($$(id_num_players));
	}
}

function OnSubmit(event) {
	// Remove the templates from the submission
	if ($$("templatePlayersTable")) $$("templatePlayersTable").remove();
	if ($$("templateTeamsTable")) $$("templateTeamsTable").remove();
	if ($$("templateTeamPlayersTable")) $$("templateTeamPlayersTable").remove();

	// Remove and elements flagged as NoSubmit by class
	var killthem = document.getElementsByClassName("NoSubmit");
	for (var i = 0; i < killthem.length; i++) killthem[i].disabled = true;

	// Tidy up the submission to meet Django formset expectations (to simplify processing when submitted)
	var team_switch = $$(id_team_switch);
	var team_play = team_switch.checked;

	if (team_play) {
		if ($$('divIndividualPlay')) $$('divIndividualPlay').remove();

		num_teams = $$(id_num_teams).value

		var idTable = 'tblTeamsTable';
    	var Table = $$(idTable);
		var p = 0;

		// Process players (performances) in two passes, capturing all those with IDs first and then those without
		// Django expects INITIAL_FORMS and TOTAL_FORMS and the first INITIAL_FORMS items it needs IDs for and the 
		// rest it will create IDs for.

		// TODO: Remove players from a team on Edit. Test this. It's not clean and I know it doesn't work.
		for (var pass = 0; pass < 2; pass++)
			for (var i = 0; i < num_teams; i++) {
	            var boxNumPlayers = findChildByName(Table, name_num_team_players.replace(form_number,i));

	            var num_players = boxNumPlayers.value;
	            var table = getParent(boxNumPlayers, "TABLE");

				var rid = getWidget(Table, name_rid, i);

	            // On Add operations remove the rid from submission as a safety.
				// Django will create ids for us when saving to the database.
				if (rid && operation === "add") rid.remove();

	    		for (var j = 0; j < num_players; j++) {
	    			var rowid = i + "." + j;

	    			// pid is found on first pass, but then if it has value was renamed so that on second pass only those without value are left
	    			var pid = getWidget(Table, name_pid, rowid);

	    			if ((pass == 0 && pid.value) || (pass == 1 && pid)) {
		    			// Fix the widget names from our internal i.j format to Djangos expected integer index
		    			var pid 	= fixWidget(Table, name_pid, rowid, p);
		                var player 	= fixWidget(Table, name_player, rowid, p);
		                var weight 	= fixWidget(Table, name_weight, rowid, p);

		                // Add a hidden element that submits the team index number for this Performance set
		                // so that we can later (when submitted) connect the player with other players on
		                // the same team. That is how we define teams, as a collection of players.
		                var team_num  = document.createElement("input");
		                team_num.type = "hidden";
		                team_num.value = i;
		                team_num.name = pid.name.replace("-id", "-team_num")
		                team_num.id = pid.id.replace("-id", "-team_num")
		                pid.parentNode.appendChild(team_num);

		                // On Add operations remove the pid from submission as a safety.
		                // Django will create ids for us when saving to the database.
		                if (pid && operation === "add") pid.remove();

		                p++;
	    			}
				}
	        }
	}
	else {
		if ($$('divTeamPlay')) $$('divTeamPlay').remove();

        // On Add operations remove the rid and pid for each player from submission as a safety.
		// Django will create ids for us when saving to the database.
		if (operation === "add") {
			var num_players = $$(id_num_players).value

	    	var idTable = 'tblPlayersTable'
	    	var Table = $$(idTable);

			for (var i = 0; i < num_players; i++) {
				var rid = fixWidget(Table, name_rid, i, i);
				var pid = fixWidget(Table, name_pid, i, i);

                if (rid) rid.remove();
                if (pid) pid.remove();
			}
		}
	}
}

function configureGame() {
	// Reads the global game options and ses the play mode as needed and limits the player counts as needed.
	var team_switch = $$(id_team_switch);
	
	if (game_individual_play && !game_team_play) {
		if (team_switch.checked) team_switch.click() 

		num_players = $$(id_num_players);
		if (num_players.value < game_min_players) num_players.value = game_min_players;  
		if (num_players.value > game_max_players) num_players.value = game_max_players; 
        adjustTable(num_players);		
	} else if (game_team_play && !game_individual_play) {
		if (!team_switch.checked) team_switch.click() 

		num_teams = $$(id_num_teams);
		if (num_teams.value < game_min_players/game_max_players_per_team) num_teams.value = game_min_players/game_max_players_per_team;  
		if (num_teams.value > game_max_players/game_min_players_per_team) num_teams.value = game_max_players/game_min_players_per_team; 
        adjustTable(num_teams);

		for (var i = 0; i < num_teams.value; i++) {
	    	var idTable = 'tblTeamsBody' + i;
	    	var Table = $$(idTable);
            var num_players = findChildByName(Table, name_num_team_players.replace(form_number,i));
			if (num_players.value < game_min_players_per_team) num_players.value = game_min_players_per_team;  
			if (num_players.value > game_max_players_per_team) num_players.value = game_max_players_per_team; 
            adjustTable(num_players);
		}		
	} 
	
}

function switchGame(event) {
	var selector = event.target;
	var game_pk = selector.value;
	var url = game_props_url.replace(/\d+$/, game_pk); // Replace the dummy Game PK with the selected one
	
	var REQUEST = new XMLHttpRequest();
	
	REQUEST.onreadystatechange = function () {
	    if (this.readyState === 4 && this.status === 200){
	        // the request is complete, parse data 
	        var response = JSON.parse(this.responseText);
	        
	        // and save in the global game properties
	        game_individual_play 	  = response.individual_play;
			game_team_play 			  = response.team_play;
			game_min_players 		  = response.min_players;
			game_max_players 		  = response.max_players;
			game_min_players_per_team = response.min_players_per_team;
			game_max_players_per_team = response.max_players_per_team;
			configureGame();
	    }
	};

	REQUEST.open("GET", url, true);
	REQUEST.send(null);
}

function switchMode(event) {
	var team_switch = $$(id_team_switch);

    if (team_switch.checked) {
    	var teams_table = $$(id_tbl_teams);
		var num_teams = $$(id_num_teams)
		var num_players = $$(id_num_players)
		
		// Map data from individual play to team play by grouping identical ranks into teams
    	var table = $$('tblPlayersTable');
    	var indiv_data = {} // object keyed on rank with array as value which contains [player, weight] elements 
		for (var i = 0; i < num_players.value; i++) {
			var rank = getWidget(table, name_rank, i).value;
			var player = getWidget(table, name_player, i).value;
			var weight = getWidget(table, name_weight, i).value;
			var rid = getWidget(table, name_rid, i).value;
			var pid = getWidget(table, name_pid, i).value;
			
			if (rank in indiv_data) {
				indiv_data[rank].push([player, weight, rid, pid]);
			} else {
				indiv_data[rank] = [[player, weight, rid, pid]];
			}
		}
    	
    	num_teams.value = Object.keys(indiv_data).length
		if (num_teams.value < game_min_players/game_max_players_per_team) num_teams.value = game_min_players/game_max_players_per_team;  
		if (num_teams.value > game_max_players/game_min_players_per_team) num_teams.value = game_max_players/game_min_players_per_team; 
		adjustTable(num_teams);
    	
    	// TODO: Support back transition. Edit a team session and convert it to individual play.
    	// Need to do a similar form mapping I suspect. In this case we have more ranks and the 
    	// processor will need to know to create new ranks as needed.
    	
    	// TODO: Find out how Django default form processing knows to create a new one (rank). I think we 
    	// just leave the ID off, but confirm this. 
    	
    	// TODO: Find out if Django default for processor can receive a delete signal somehow (adding a hidden field?)
		//		 Need when losing Ranks (indiv to team play conversion) to have backend tidy up properly.
    	
    	for (var i = 0; i < num_teams.value; i++) {
    		var rank = Object.keys(indiv_data)[i];

	    	var table = $$('tblTeamsBody' + i);
    		var num_players = findChildByName(table, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.
    		num_players.value = indiv_data[rank].length;
			if (num_players.value < game_min_players_per_team) num_players.value = game_min_players_per_team;  
			if (num_players.value > game_max_players_per_team) num_players.value = game_max_players_per_team; 

			
    		var rank_box = findChildByName(table, name_rank.replace(form_number,i));
    		rank_box.value = rank;

    		var name_box = findChildByName(table, name_team_name.replace(form_number,i));
    		name_box.value = "Team " + i
    		
    		// 
    		
            adjustTable(num_players);

            for (var j = 0; j < num_players.value ; j++) {
            	// Constraint checks may have added team players which we can't find in the indiv_data
            	// So lay a fallback.
            	var player;
            	try { player = indiv_data[rank][j][0]; }
            	catch(err) { player = "" }
            	
            	var weight;
            	try { weight = indiv_data[rank][j][1]; }
            	catch(err) { weight = 1 }
            	
            	var teams_table = $$(id_tbl_teams);
            	var fn = i + "." + j;
            	var player_box = findChildByName(teams_table, name_player.replace(form_number, fn));
            	var weight_box = findChildByName(teams_table, name_weight.replace(form_number,fn));
            	
            	player_box.value = player;
            	weight_box.value = weight;
            }
    	}

    	$$('divIndividualPlay').style.display = 'none';
    	$$('divTeamPlay').style.display = 'block';
    	enableChildren($$('divTeamPlay'), true);
    	enableChildren($$('divIndividualPlay'), false);
    } else {
    	var table = $$(id_tbl_players);
		var num_players = $$(id_num_players)
		
		// TODO: Map data from team play to individual play stipping out the teams layer

		
		if (num_players.value < game_min_players) num_players.value = game_min_players;  
		if (num_players.value > game_max_players) num_players.value = game_max_players; 
		adjustTable(num_players);

    	$$('divTeamPlay').style.display = 'none';
    	$$('divIndividualPlay').style.display = 'block';
    	enableChildren($$('divIndividualPlay'), true);
    	enableChildren($$('divTeamPlay'), false);
    }
}

function OnRowcountChange(event) {
	Table = adjustTable(event.target);

	// TODO: Diagnose - This fails. Want to add 2 players to newly added teams. How?
	if (event.target.id === id_num_teams) {
		for (var i = 0; i < event.target.value; i++) {
		    var boxNum = findChildByName(Table.parentNode, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.

		    adjustTable(boxNum);
		}
	}
}

function OnPlayerChange(event) {
	var player_copy_id = event.target.id.replace(performance_prefix, rank_prefix);
	var player_copy = $$(player_copy_id);
	player_copy.value = event.target.value;
}

function showhideTeamPlayers(event) {
    var checked = event.target.checked;
    var rowTeam = getParent(event.target,"TR");
    var numTeam = getRowId(rowTeam.id);
    var idTeamPlayers = "tblTeamPlayersTable" + numTeam;
    var tblTeamPlayers = $$(idTeamPlayers);

    if (tblTeamPlayers != null) {
        tblTeamPlayers.style.display = (checked ? 'block' : 'none');
    }
}

function createTable(template, id, placein) {
    var table = document.createElement('table');
    table.id = id;
    table.className = template.className;
    table.style = template.style;

    placein.appendChild(table);

    return table;
}

function updateManagementForms(div) {
    // Keep the Django Management form totals up to date. rows is the number of form elements in either:
    // Ranks - if the template is PlayersTable or TeamsTable
    // Performance - if the template is PlayersTable or TeamPlayersTable
    // When this is an "add" form we update the INITIAL management form values as well.
    // When it's an "edit" form these will be set already by Django to the correct counts
    // When it's an "add" form Django sets them to the count of objects in the database (rather than 0)
    // But as we are creating an initial form with Javascript we MUST update the INITIAL values too to be 0 for Django to read these as creations and generate primary keys
    var rinit = findChildByName(div, name_rinit);
    var pinit = findChildByName(div, name_pinit);
    var rtotal = findChildByName(div, name_rtotal);
    var ptotal = findChildByName(div, name_ptotal);

    // On an add operation, rinit and pinit come in oddly as the total number of Rank and Performance items respectively in the database.
    // Django needs them to be 0 to understand that the Ranks and Performances submitted are new and need new primary keys
	if (operation === "add") {
		rinit.value = 0;
		pinit.value = 0;
	}

    if (div.id === "divIndividualPlay" ) {
    	var num_players = $$(id_num_players).value;
    	rtotal.value = num_players;
    	ptotal.value = num_players;
    } else if (div.id === "divTeamPlay" ) {
    	var num_teams = $$(id_num_teams).value;
    	rtotal.value = num_teams;

    	var p = 0;
		for (var i = 0; i < num_teams; i++) {
	    	var idTable = 'tblTeamsBody' + i;
	    	var Table = $$(idTable);
            var boxNum = findChildByName(Table, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.
    		p += parseInt(boxNum.value);
        }
		ptotal.value = p;
    }
}

function drawTable(template, rows, placein, rowno) {
	var idTable = template.id.replace("template", "tbl");
    if (rowno != null) idTable = idTable + rowno;

    var NewTable = $$(idTable) == null;

    if (NewTable) {
        table = createTable(template, idTable, placein);
    } else if (rows > 0) {
        table = $$(idTable);
    }

    // get the details row. Exists only for "number of teams" not for "number of players" calls.
    var trd = $$(template.id.replace("Table", "Detail"));  // Has a value only in Team play mode (is the TeamsDetail row which has the number box for count of teams)
    var isNumTeams = (trd != null);

    // "rows" is the number typed into the Number of Players/Teams box,
    //		for Number of teams: we need 2 rows per team, one for the team rank and name, and one for the details (player list).
    //		for Number of players: we need 1 row per player
    // In both cases we need a header row.
    var rowsNeeded = (isNumTeams ? 2*rows : rows) + 1;
    var rowsPresent = table.rows.length;

    if (rowsNeeded < rowsPresent) {
    	// Destroy the excess rows (means that if we reduce the number of rows and then increase them again any data in them will be lost.
        var rem = rows <= 1 ? rowsPresent : rowsPresent - rowsNeeded;
        for (i = 0; i < rem; i++) {
            table.deleteRow(-1);
        }
    } else if (rowsNeeded > rowsPresent) {
    	// Add the missing rows
        var trh = $$(template.id.replace("Table", "Header"));    // The template table header row
        var trb = $$(template.id.replace("Table", "Body"));		 // The template table body row

        // Build a header row first if it doesn't already exist!
        if (rowsPresent == 0) {
            var TRH = trh.cloneNode(true);
            TRH.id = trh.id.replace("template", "tbl");
            TRH.className = trh.className;
            TRH.style = trh.style;

            table.appendChild(TRH);
            rowsNeeded--;
        }

		// Now lets work out how many steps of "adding" rows we need
        var steps;  	// The number of steps we'll need to take
        if (trd != null) {    							// Team play mode
        	steps = (rowsNeeded - rowsPresent) / 2; 	// Build the rows in pairs
        } else {										// Individual  play mode
        	steps = rowsNeeded - rowsPresent;			// Build one row per step
        }

        for (i = 0; i < steps; i++) {
        	// Build a rowid that will be added to the element IDs
            var rowid;
            if (rowsPresent > 1) {
            	if (trd != null) rowid = i + (rowsPresent - 1)/2;
            	else rowid = i + rowsPresent - 1;
            } else {
            	rowid = i
            }
            rowid = (rowno == '' ? '' : (rowno + '.')) + rowid;

            var TRB = trb.cloneNode(true);
            TRB.id = trb.id.replace("template", "tbl") + rowid;
            TRB.className = trb.className;
            TRB.style = trb.style;

            // Get the widgets in TRB:
            var rid = fixWidget(TRB, name_rid, rowid);            		// This is the ID of the rank entry in the database. Needed when editing sessions (and the ranks associated with them)
            var pid = fixWidget(TRB, name_pid, rowid);            		// This is the ID of the performance entry in the database. Needed when editing sessions (and the ranks associated with them)
            var rank = fixWidget(TRB, name_rank, rowid);          		// This is the rank itself, a dango field for generic processing, but with a default value added when created here as well
            var player = fixWidget(TRB, name_player, rowid);      		// This is the name/id of the player with that rank, a dango field for generic processing
            var player_copy = fixWidget(TRB, name_player_copy, rowid);	// This is a copy of the player we need to keep of player (see header for details)
            var weight = fixWidget(TRB, name_weight, rowid);      		// This is the partial play weighting, a dango field for generic processing
            var team = fixWidget(TRB, name_team_name, rowid);     // 		This is the name of the team. Optional in the database and it an stay a local field for specific (non-generic) processing when submitted.

            if (TRB.className === 'players') {
            	if (debug) alert("players: " + TRB.id);
            	var rankid = parseInt(rowid);
            	var defaultrank = rankid+1;

                rid.value 	 = rIDs === null 			? "" 	 		: (defaultrank > rIDs.length 	? ""			: rIDs[rowid]);
                pid.value 	 = pIDs === null 			? "" 	 		: (defaultrank > pIDs.length 	? ""			: pIDs[rowid]);
                rank.value 	 = Ranking === null 		? defaultrank 	: (defaultrank > Ranking.length ? defaultrank 	: Ranking[rowid]);

                player.value = Players === null || rowid > Players.length 	? "" : Players[rowid];
                weight.value = isNaN(parseInt(player.value)) ? 1 : Weights[Players.indexOf(parseInt(player.value))];
                player_copy.value = player.value;
            } else if (TRB.className === 'team') {
            	if (debug) alert("team: " + TRB.id);

                var players = fixWidget(TRB, name_num_team_players, rowid); // This is the number TRB players in the team. Used only in form processing.

            	var rankid = parseInt(rowid);
            	var defaultrank = rankid+1;

                rid.value  = rIDs === null 	   ? "" 	 		: (defaultrank > rIDs.length ? "" : rIDs[rowid]);
                rank.value = Ranking === null  ? defaultrank 	: (defaultrank > Ranking.length ? defaultrank 	: Ranking[rowid]);
                team.value = Teams == null     ? "" : defaultrank > Teams.length ? team.value 	: Teams[rowid];
                players.value = TeamPlayers == null || defaultrank > TeamPlayers.length  ? 2 : TeamPlayers[rowid].length
            } else if (TRB.className === 'teamplayers') {
            	if (debug) alert("teamplayers: " + TRB.id);

                var rownum_Team = getPart(1, rowid);
                var rownum_TeamPlayer = getPart(2, rowid);

                // Find Player ID first so we can use it to find the index into the Weights and pID lists
                player.value = rownum_Team < TeamPlayers.length && rownum_TeamPlayer < TeamPlayers[rownum_Team].length ? TeamPlayers[rownum_Team][rownum_TeamPlayer] : "";
                weight.value = isNaN(parseInt(player.value)) ? 1 : Weights[Players.indexOf(parseInt(player.value))];
                pid.value    = isNaN(parseInt(player.value)) ? "" : pIDs[Players.indexOf(parseInt(player.value))];
            } else {
            	if (debug) alert("Huh? " + TRB.id);
            }

            enableChildren(TRB, true);

            table.appendChild(TRB);

            // Add the second row, the (empty) Detail row if needed for added Teams
            if (isNumTeams) {
                var TRD = trd.cloneNode(true);
                TRD.id = trd.id.replace("template", "tbl") + rowid;

                var TCDid = trd.id.replace("template", "tbl") + "Cell" + rowid;
                TRD.children[0].id = TCDid;

                table.appendChild(TRD);
            }
        }
    }

    // Update the Django Management forms
    updateManagementForms(getParent(table, 'DIV'));

    // Return the table that was drawn
    return(table);
}

function adjustTable(element) {
    var td = getParent(element, "TD");
    var tr = getParent(td, "TR");
    var tableControl = getParent(tr, "TABLE");

    var mapTemplate = {"tblIndividualPlay":"templatePlayersTable", "tblTeamPlay":"templateTeamsTable", "tblTeamsTable":"templateTeamPlayersTable"};

    var FormNumber = getFormNumber(element.name);
    var idTemplate = mapTemplate[tableControl.id];
    var idTable = idTemplate.replace("template","tbl") + FormNumber;

    var template = $$(idTemplate);
    var table = $$(idTable);

    var placein;
    if (idTemplate === "templateTeamPlayersTable") {
        placein = $$(tr.id.replace("Body","DetailCell"));
    } else {
        placein = template.parentNode;
    }

    var text = element.value;
    var intMatches = text.match(/^\d+$/);

    if (intMatches === null) {
        table.style.display = 'none';
        element.value = "Please enter a whole number.";
    } else {
        var numRows = Number(intMatches[0]);								// The number of teams or players being requested
        var minRows = idTemplate === "templateTeamPlayersTable" ? 1 : 2;	// We need a minium of 2 ranking teams or players, but in TeamPlay mode a team of 1 is OK

        if (numRows >= minRows) {
            var rowID = getRowId(tr.id);									// The row number of the rank entry (team or player) is encoded in the row ID

            drawTable(template, numRows, placein, rowID);
            if (idTemplate === "templateTeamPlayersTable") {
                var chkShowTeamPlayers = findChildByName(tr,'ShowTeamPlayers');
                chkShowTeamPlayers.checked = true;
            }
        }
    }

    // Return the table that was adjusted
    return(tableControl);
}

// Enable or disable a control and all its children
function enableChildren(of, enable) {
	if ((/^template/).test(of.id)) return;  // Don't fix a template only a clone that's been renamed

    of.disabled = (enable === undefined) ? true : !enable;

    var children = of.children;
    for (var i = 0; i < children.length; i++)
    	enableChildren(children[i], enable);
}

//Get the Django widget with a give name inside a given element
function getWidget(inside, name, rowid) {
	return rowid == null ? findChildByName(inside, name) : findChildByName(inside, name.replace(form_number, rowid));
}

// Get the Django widget with a give name inside a given element, and update it with the give row id.
function fixWidget(inside, name, rowid, newrowid) {
	var widget = newrowid == null ? findChildByName(inside, name) : findChildByName(inside, name.replace(form_number, rowid));

	if (widget != null) {
		var from = newrowid == null ? form_number : rowid;
		var to   = newrowid == null ? rowid : newrowid;
		widget.id     = widget.id.replace(from,to);
		widget.name   = widget.name.replace(from,to)
		return widget;
	} else return null;
}

// Find an an element with a given name which is a child of a specified element
function findChildByName(element, name) {
    if (element.name !== undefined && element.name === name) return element;

    var children = element.children;
    for (var i = 0; i < children.length; i++)
    {
        var result = findChildByName(children[i], name);
        if (result != null) return result;
    }	
}

function getParent(of, type) {
    var parent = of;
    do {
        parent = parent.parentNode;
    } while (parent.tagName !== type && parent !== document);
    return parent;
}

//Get the row id from an id or name string. e.g. ThisisRow4 -> 5
function getRowId(of) {
    var matches = of.match(/^.*?(\d*)$/);
    return matches === null ? "" : matches[1];
}

// Get part 1 or 2 of an n.m string
function getPart(part, of) {
    var matches = of.match(/^(\d*)\.(\d*)$/);
    return matches === null ? "" : matches[part];
}

//Get the form number from a name in the format Model-FormNumber-FieldName
function getFormNumber(of) {
    var matches = of.match(/^(.*?)\-(\d*)\-(.*?)$/);
    return matches === null ? "" : matches[2];
}

function $$(id) {
//    return document.getElementById(id);
//  or using jQuery:
    return $('#'+	id)[0];
}
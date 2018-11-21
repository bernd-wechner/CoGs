"use strict";

const debug = false;

// Note: The Django Generic widgets are created by Django with __prefix__ conveniently in the widget name
//       where the Django formset saver expects to find a form identifier. Replacig this with a number which
//		 is consistent for all widgets inside of one form in a formset associates them all. The should be 
//		 numbered 0, 1, 2, 3 etc ...  

const id_prefix   =	 "id_";				// This is the prefix to element ID strings Django formsets use. A form element has "id=id_yadayada name=yadayada" properties
const form_number = '__prefix__';		// This should be replaced by the number of the form, 0, 1, 2, 3 and so on for each form in the formset

// Specify the related model prefixes used in field names
const rank_prefix 		 = "Rank-"
const performance_prefix = "Performance-"
const team_prefix 		 = "Team-"

// Define some widget names and ids. form_number will be replaced by the form number when new ones are created.
// 		On edit, we need to put the IDs of the Rank and Performance objects on the form so that on save we know which ones to save.
// 		We don't need to do this for Team objects as Teams are defined by	 their members, i.e the Player IDs and these are stored in the Player field itself.
const name_rid     		  = rank_prefix + form_number + '-id';          // The Ranking ID in the database (ranks are stored in a model of their own, called Rank)
const name_pid      	  = performance_prefix + form_number + '-id';   // The Performance ID in the database (partial play weights are stored in a model of their own called Performance)
const name_tid  	  	  = team_prefix + form_number + '-id';			// The Team ID in the database (if iediting a team play session)

const id_rid     		  = id_prefix + name_rid;                       // The Ranking ID in the database (ranks are stored in a model of their own, called Rank)
const id_pid      	      = id_prefix + name_pid;                 		// The Performance ID in the database (partial play weights are stored in a model of their own called Performance)
const id_tid  	  	      = id_prefix + name_tid;						// The Team ID in the database (if iediting a team play session)

//The Django management form fields we need to keep up to date reflecting the number of forms in the formset if we want Django to save them for us
const name_rinit     	  = rank_prefix + "INITIAL_FORMS";
const name_pinit     	  = performance_prefix + 'INITIAL_FORMS';
const name_tinit     	  = team_prefix + 'INITIAL_FORMS';
const name_rtotal     	  = rank_prefix + "TOTAL_FORMS";
const name_ptotal     	  = performance_prefix + 'TOTAL_FORMS';
const name_ttotal     	  = team_prefix + 'TOTAL_FORMS';

// TODO: name_player_copy keeps a Rank copy for the player id. We need a analagous team copy name_tid_copy methinks!

// Actual model fields
const name_rank   		  = rank_prefix + form_number + '-rank';						 	// Ranking (1st, 2nd, 3rd)
const name_player     	  = performance_prefix + form_number + '-player';	                // Player name/id in the Performance object (and the the selector)
const name_player_copy    = rank_prefix + form_number + '-player';	                        // Player name/id in the Rank object in individual play mode (copied from name_player on submit)
const name_weight 		  = performance_prefix + form_number + '-partial_play_weighting'; 	// Partial play weighting (0-1)

const id_rank 		      = id_prefix + name_rank;
const id_player 		  = id_prefix + name_player;
const id_player_copy	  = id_prefix + name_player_copy;
const id_weight 		  = id_prefix + name_weight;

const name_team_name  	  	= team_prefix + form_number + '-name';
const name_num_team_players = team_prefix + form_number + '-num_players';

const id_team_name 		   = id_prefix + name_team_name;
const id_num_team_players  = id_prefix + name_num_team_players;

// Define the IDs of some vital control elements for the smooth operation of the form.
const id_indiv_div		  = "divIndividualPlay";										// The div displayed in individual mode
const id_teams_div 		  = "divTeamPlay";												// The div displayed in team mode 

const id_indiv_tbl		  = "tblIndividualPlay";										// The table for individual mode
const id_teams_tbl 		  = "tblTeamPlay";												// The table for team mode 

const id_num_players	  = "NumPlayers";												// ID of the field that contains the number of players (in in Individual Play mode)
const id_num_teams		  = "NumTeams";													// ID of the field that contains the number of teams (in in Team Play mode)

const id_tbl_players 	  = "tblPlayersTable";											// ID of the table that contains the players (in in Individual Play mode)
const id_tbl_teams 		  = "tblTeamsTable";											// ID of the table that contains the teams (in in Team Play mode)

const id_team_switch  	  = id_prefix + 'team_play';								 	// The checkbox used to switch between Individual play mode and Team play mode

// Add some useful derived globals (that are set in configureGame if a new game is selected)
let game_min_teams = Math.max(game_min_players/game_max_players_per_team,2);
let game_max_teams = Math.max(game_max_players/game_min_players_per_team, 2);

// Add event listeners to initialize the form and to tidy it on submit
window.addEventListener('load', OnLoad, true);
window.addEventListener('submit', OnSubmit, true);

function OnLoad(event) {
	const team_switch = $$(id_team_switch);
	team_switch.addEventListener('click', switchMode)
	
	const game_selector = $$(id_prefix+"game");
	game_selector.addEventListener('change', switchGame)
	
	if (operation === "edit") {		
		if (is_team_play) {
			$$(id_indiv_div).style.display = 'none';
			$$(id_teams_div).style.display = 'block';
			
			// Constrain the supplied data to expected bounds 
			let num_teams = Session["rIDs"].length; // one rank per team
			if (num_teams < game_min_teams) num_teams = game_min_teams;  
			if (num_teams > game_max_teams) num_teams = game_max_teams; 
			$$(id_num_teams).value = num_teams;
	
			// This will create the teams table with a header row and 2 rows per team (body and details).		
			adjustTable($$(id_num_teams));
	
			// For each team build the Team players table.
			// which goes on the details row of the teams table just created, in the teams detail cell. 
			for (let i = 0; i < num_teams; i++) {
				const rID = Session["rIDs"][i];
				const tID = Session["Teams"][rID];
				let num_players = Session["TeamPlayers"][tID].length;
				if (num_players < game_min_players_per_team) num_players = game_min_players_per_team;  
				if (num_players > game_max_players_per_team) num_players = game_max_players_per_team; 
				
				if (num_players > 0) {
			    	const idTable = 'tblTeamsBody' + i;
			    	const Table = $$(idTable);
	
			    	// This is the number of players in the team. Used only in form processing.
			    	const real_name_num_team_players = name_num_team_players.replace(form_number,i);
			    	const boxNum = findChildByName(Table, real_name_num_team_players); 	
	
	                boxNum.value = num_players;
	
	                adjustTable(boxNum);
	            }
	        }
		} else {
			$$(id_teams_div).style.display = 'none';
			$$(id_indiv_div).style.display = 'block';
	
			// Constrain the supplied data to expected bounds 
			const min_players = game_min_players;
			const max_players = game_max_players;			
			let num_players = Session["rIDs"].length; // one rank per player
			if (num_players < min_players) num_players = min_players;  
			if (num_players > max_players) num_players = max_players; 
	    	$$(id_num_players).value = num_players;
	    	$$(id_num_players).defaultValue = num_players;
	
	        adjustTable($$(id_num_players));
		}
		
		team_switch.disabled = (!game_individual_play || !game_team_play);
	} else
		// Make sure the game is properly configured
		configureGame();
	
	team_switch.disabled = false;
}

function OnSubmit(event) {
	// Remove the templates from the submission
	if ($$("templatePlayersTable")) $$("templatePlayersTable").remove();
	if ($$("templateTeamsTable")) $$("templateTeamsTable").remove();
	if ($$("templateTeamPlayersTable")) $$("templateTeamPlayersTable").remove();	

	// Remove and elements flagged as NoSubmit by class
	const killthem = document.getElementsByClassName("NoSubmit");
	for (var i = 0; i < killthem.length; i++) killthem[i].disabled = true;

	// Tidy up the submission to meet Django formset expectations (to simplify processing when submitted)
	const team_switch = $$(id_team_switch);
	const team_play = team_switch.checked;
	
	// TODO work out where placehold IDs should be checked for and blanked out.
	if (team_play) {
		const num_teams = $$(id_num_teams).value
    	const tbl_teams = $$(id_tbl_teams);
				
		// Keep a count ranks, performancs and teams we've requested deletion of 
		// (so we can number the forms properly, sort of like num_teams+deleted_ranks)
		let	deleted_ranks = 0;
		let	deleted_perfs = 0;
		let	deleted_teams = 0;

		// A performance pointer that helps us keep a list of perfs to upate followed by perfs to create 
		let P = 0;
		
		// Process players (performances) in two passes, capturing all those with IDs first and then those without
		// Django expects INITIAL_FORMS and TOTAL_FORMS and the first INITIAL_FORMS items it needs IDs for and the 
		// rest it will create IDs for.
		for (let pass = 0; pass < 2; pass++)
			for (let t = 0; t < num_teams; t++) {
	            const box_num_players = findChildByName(tbl_teams, name_num_team_players.replace(form_number,t));
	            const num_players = box_num_players.value;

	            // Rank ID management only needs to happen once on the first pass
	            if (pass == 0) {
					const rid = getWidget(tbl_teams, name_rid, t);
		            // On Add operations remove the rid from submission as a safety.
					// Django will create ids for us when saving to the database.
					if (operation === "add") 
						rid.remove();
					else {					
						// If we're editing, we had Rank IDs and now we may have some folded Ranks IDs 
						// after a conversion from individual play to team play. These we have to unfold, 
						// which means we keep the first one and request the remaining rank objects be deleted.
						const rids = rid.value.split("&");
						if (rids.length > 1) {
							rid.value = rids[0];						
							for (let r=1; r<rids.length; r++) {
								// Add a hidden pair of elements that convey the rank ID and the -DELETE request.
								// We need to use form numbers above those used by actual forms, so starting with
								// num_teams. That is forms 0, 1, 2 ... num_teams-1 will all have a rank for a team.
								// And forms num_teams,num_teams+1, num_teams+2 ... Are ones we can add delete 
								// requests for. But we need to keep track of how many we've deleted.
								const fn = Number(num_teams)+Number(deleted_ranks);
								
								// TODO: reconsider the need for this, lost some in indiv mode as id was already there
				                const rank_id = document.createElement("input");
				                rank_id.type 	= "hidden";
				                rank_id.value 	= rids[r];
				                rank_id.id 		= id_rid.replace(form_number, fn)
				                rank_id.name	= name_rid.replace(form_number, fn)
				                rid.parentNode.appendChild(rank_id);
	
				                // TODO: Make this a hidden checkbox like in indiv mode
				                const rank_del = document.createElement("input");
				                rank_del.type 	= "hidden";
				                rank_del.value 	= "on";
				                rank_del.id 	= rank_id.id.replace("-id", "-DELETE");
				                rank_del.name 	= rank_id.name.replace("-id", "-DELETE");
				                rid.parentNode.appendChild(rank_del);
	
				                deleted_ranks++;
							}
						}
					}
	            }

	            // Now on both passes we look at all players, but on pass one we build up P = 0, 1,2 ,3 ... n
	            // until we've used all the PIDs, then on the second we'll continue with P = n, n+1, n+2 ... m
	    		for (let p = 0; p < num_players; p++) {
	    			// pid is found on first pass, but then if it has value was renamed 
	    			// so that on second pass only those without value are left
	    			const cfn = t + "." + p;							// Compound Form Number
	    			const pid = getWidget(tbl_teams, name_pid, cfn);

	    			// On first pass do those which have a pid are grouped as form numbers 0, 1, 2, ... n
	    			// On the second pass those that are left get form numbers n+1, n+2, n+3 ...
	    			// 
	    			// On the first pass we rename the pid widget from a t.p form_number to p
	    			// On the second pass those pids renamed on first pass are no longer found and pid is undefined
	    			// It is only pids that have no value that remain defined on the second pass.
	    			if ((pass == 0 && pid.value) || (pass == 1 && pid)) {
		    			// Fix the widget names from our internal t.p format to Django's expected integer index
		    			const pid 	 = fixWidget(tbl_teams, name_pid,    cfn, P);
		    			const player = fixWidget(tbl_teams, name_player, cfn, P);
		    			const weight = fixWidget(tbl_teams, name_weight, cfn, P);
		    			P++;

		                // Add a hidden element that submits the team index number for this Performance set
		                // so that the server can later (when submitted) associate the player with other players 
		    			// on the same team. That is how we define teams, as a collection of players.
		                const team_num  = document.createElement("input");
		                team_num.type 	= "hidden";
		                team_num.value 	= t;
		                team_num.id 	= pid.id.replace("-id", "-team_num")
		                team_num.name 	= pid.name.replace("-id", "-team_num")
		                pid.parentNode.appendChild(team_num);

		                // On Add operations remove the pid from submission as a safety.
		                // Django will create ids for us when saving to the database.
		                if (pid && operation === "add") pid.remove();
	    			}
				}
	    		
	    		// On the second pass after P has reached m, we can look for any deleted performances
	    		// and add delete forms numbered m+1, m+2, m+3 ... Of course we only have performances 
	    		// to delete on an edit operation not if we are adding (started with a blank form)
	    		if (operation == "edit" && pass == 1) {
					// we'll look in the teamplayer trash for any deleted players (performances)
					const id_template = "templateTeamPlayersTable";
					const id_table = id_template.replace("template", "tbl") + t;
					const id_trash = id_table.replace("tbl", "trash");
					const table = $$(id_table);
					const trash = $$(id_trash);
					const count = trash.rows.length;

					for (let p = 0; p < count; p++) {
			            const row = trash.row[p];
			            
			            // In the trash the pid is in an element with id = name_pid, but
			            // that contains an unknown form number, so we'll search for it with the
			            // prefix and suffix, expect one result and use that to the value 
			            const pid = row.querySelectorAll("[id^=['"+id_prefix+performance_prefix+"'][id$='-id']")[0];
			            
						// Add a hidden pair of elements that convey the rank ID and the -DELETE request.
						// We need to use form numbers above those used by actual forms, so starting with
						// num_teams. That is forms 0, 1, 2 ... num_teams-1 will all have a rank for a team.
						// And forms num_teams,num_teams+1, num_teams+2 ... Are ones we can add delete 
						// requests for. But we need to keep track of how many we've deleted.
		                const perf_id = document.createElement("input");
		                perf_id.type 	= "hidden";
		                perf_id.value 	= pid.value;
		                perf_id.id 		= id_pid.replace(form_number, P)
		                perf_id.name	= name_pid.replace(form_number, P)
		                table.appendChild(perf_id);

		                const perf_del = document.createElement("input");
		                perf_del.type 	= "hidden";
		                perf_del.value 	= "on";
		                perf_del.id 	= perf_id.id.replace("-id", "-DELETE");
		                perf_del.name	= perf_id.name.replace("-id", "-DELETE");
		                table.appendChild(perf_del);
		                
		                P++; deleted_perfs++;
					}											    			
	    		}
	        }

		if (operation == "edit") {
			// We may also have deleted teams! If so, we'll find them in the team trash and need 
			// to process them, requesting that the associated Rank objects be deleted.
			const id_template = "templateTeamsTable";
			const id_table = id_template.replace("template", "tbl");
			const id_trash = id_table.replace("tbl", "trash");
			const table = $$(id_table);
			const trash = $$(id_trash);
			const count = trash.rows.length;
			
			for (let t = 0; t < count; t++) {
	            const row = trash.row[t];
			
	            // In the trash the rid is in an element with id = name_rid, but
	            // that contains an unknown form number, so we'll search for it with the
	            // prefix and suffix, expect one result and use that to the value 
	            const rid = row.querySelectorAll("[id^=['"+id_prefix+rank_prefix+"'][id$='-id']")[0];
			
				// Add a hidden pair of elements that convey the rank ID and the -DELETE request.
				// We need to use form numbers above those used by actual forms, so starting with
				// num_teams. That is forms 0, 1, 2 ... num_teams-1 will all have a rank for a team.
				// And forms num_teams,num_teams+1, num_teams+2 ... Are ones we can add delete 
				// requests for. But we need to keep track of how many we've deleted.
	            const rank_id = document.createElement("input");
	            rank_id.type 	= "hidden";
	            rank_id.value 	= rid.value;
	            rank_id.id 		= id_rid.replace(form_number, num_teams+deleted_ranks)
	            rank_id.name	= name_rid.replace(form_number, num_teams+deleted_ranks)
	            table.appendChild(rank_id);
	
	            const rank_del = document.createElement("input");
	            rank_del.type 	= "hidden";
	            rank_del.value 	= "on";
	            rank_del.id 	= rank_id.id.replace("-id", "-DELETE");
	            rank_del.name	= rank_id.name.replace("-id", "-DELETE");
	            table.appendChild(rank_del);

	            // Same deal for team IDs
	            const tid = row.querySelectorAll("[id^=['"+team_prefix+"'][id$='-id']")[0];
			
				// Add a hidden pair of elements that convey the team ID and the -DELETE request.
	            const team_id = document.createElement("input");
	            team_id.type 	= "hidden";
	            team_id.value 	= tid.value;
	            team_id.id 		= id_tid.replace(form_number, num_teams+deleted_ranks)
	            team_id.name	= name_tid.replace(form_number, num_teams+deleted_ranks)
	            table.appendChild(team_id);
	
	            const team_del = document.createElement("input");
	            team_del.type 	= "hidden";
	            team_del.value 	= "on";
	            team_del.id 	= team_id.id.replace("-id", "-DELETE");
	            team_del.name 	= team_id.name.replace("-id", "-DELETE");
	            table.appendChild(team_del);
	            	            
	            deleted_ranks++; deleted_teams++;
			}
			
			// Finally if submitting teams tidy up the submission a tad. may have 
			// some mock IDs and names in place auto filled from either a conversion
			// from individual play (in the case of Team IDs) or simply a form creation 
			// (in the the case of Team Name). Neither should be submitted in that form
			for (let t=0; t<num_teams; t++) {
				const team_id 		= getWidget(tbl_teams, name_tid, t);
				const team_name  	= getWidget(tbl_teams, name_team_name, t);
				
				team_id.value 	= /^id_\d+$/.test(team_id.value) 		? "" : team_id.value;
				team_name.value = /^Team \d+$/.test(team_name.value) 	? "" : team_name.value; 
			}			
		}
		
		// We have to add the number of deleted forms to the TOTAL_FORMS field in the management form
		// or Django will ignore them (i.e. only process TOTAL_FORMS forms not these extra ones.
		updateManagementForms($$(id_teams_div));		
		
		// Remove the individual play form completely before submitting
		if ($$(id_indiv_div)) $$(id_indiv_div).remove();
	} 
	else { // it's individual play
		const num_players = Number($$(id_num_players).value);
		
        // On Add operations remove the rid and pid for each player from submission as a safety.
		// Django will create ids for us when saving to the database.
		if (operation === "add") {
	    	const id_table = 'tblPlayersTable'
	    	const table = $$(id_table);

			for (var p = 0; p < num_players; p++) {
				const rid = getWidget(table, id_rid, p);
				const pid = getWidget(table, id_pid, p);

                if (rid) rid.remove();
                if (pid) pid.remove();
			}
		} else {
			// It's an individual play mode session being submitted but it may have been 
			// a team play session when loaded (if this is an edit form).
			//
			// In that case there may be teams that are no longer relevant and need deletion
			// and ranks certainly need updating from team to player references. The latter
			// must be done server side, on client side here we can check for any deleted
			// teams and ensure we add -DELETE requests to the submission.
			//
			// The server should only delete such teams of coursem if there are no references 
			// left to that team and so these -DELETE requests still need server side attention.
			//
			// is_team_play is true only if session.team_play of the session loaded for editing
			// is true. Nabbed from context in the template that loads this JS file.
			if (is_team_play) {
				// They could be in either the teams table or the teams trash really depending on
				// the edits that happened before it was made an individual play session. All teams
				// be they in the teams table or the teams trash table are no longer needed and can
				// be marked for deletion in the server submission.
				const id_template = "templateTeamsTable";
				const id_table = id_template.replace("template", "tbl") + t;
				const id_trash = id_table.replace("tbl", "trash");
				const table = $$(id_table);
				const trash = $$(id_trash);

		    	const div_players = $$(id_indiv_div);				
				
				let T = 0;
				for (let tbl of [table, trash]) {
					for (row of tbl.rows) {
						// There's a hidden element holding the Team ID with an id in the format:
						// 		id_Team-n-id
						// which is generalsied to the pattern:
						//		id_prefix+team_prefix+ n +"-id"
						// We have one row of a teams or trash table here and it has one tid element
						// in it with one form_number n. We don't care what that form number is, only
						// want to find the element and extract the team ID from it if there.
			            const tid = row.querySelectorAll("[id^='"+id_prefix+team_prefix+"'][id$='-id']")[0];

			            // If the TID element has no value then we have no team to delete, but if it does ...
			            // the TID element has no value on add froms and on teams that were added on an edit form
			            // by increasing the number of teams.
			            if (tid.value) {
				            // Add a hidden pair of elements (that convey the team ID and the -DELETE request)
				            // to the submitted division (individual play mode session). These will identify
				            // the team and request its deletion and must be in the submitted division
				            // (only one of $$(id_indiv_div) or $$(id_team_div) will be submitted.
			                const team_id = document.createElement("input");
			                team_id.type 	= "hidden";
			                team_id.value 	= tid.value;
			                team_id.id 		= id_tid.replace(form_number, T)
			                team_id.name	= name_tid.replace(form_number, T)
			                div_players.appendChild(team_id);
	
			                const team_del = document.createElement("input");
			                team_del.type 	= "checkbox";
			                team_del.value 	= "on";
			                team_del.id 	= team_id.id.replace("-id", "-DELETE");
			                team_del.name	= team_id.name.replace("-id", "-DELETE");
				            team_del.style.display = 'none';
			                div_players.appendChild(team_del);
			                
			                T++;
			            }
					}
				}								
			} 
			else { // we are editing a session that had session.team_play=false when the form was initialised. 
				// We have to check the trash for deleted players. We have a 
				// rank ID and a performance ID for each one that we need to 
				// request the deletion of.
				const id_template = "templatePlayersTable";
				const id_table = id_template.replace("template", "tbl");
				const id_trash = id_table.replace("tbl", "trash");
				const table = $$(id_table);
				const trash = $$(id_trash);
				const count = trash.rows.length;

				let	deleted_ranks = 0;
				let	deleted_perfs = 0;
							
				for (let t = 0; t < count; t++) {
		            const row = trash.rows[t];
		
		            // In the trash row the rid and pid elements have an unknown form number
		            // embedded in the id so we have to find it with a pattern match.
		            // The ids of the elelements that contain rank and performance ids resemble:
		            //    id_Rank-n-id
		            //    id_Performance-n-id
		            // where n is the form (row) number and we are looking here at one row in the
		            // trash that has one of each of these elements. We find them to extract the ids of
		            // the rank and performance we need to request deletion of.
		            const rid = row.querySelectorAll("[id^='"+id_prefix+rank_prefix+"'][id$='-id']")[0];
		            const pid = row.querySelectorAll("[id^='"+id_prefix+performance_prefix+"'][id$='-id']")[0];
				
		            // Only request a deletion if the rid has a value (was not not added during this edit session)
		            if (rid.value) {
						// Add a hidden checkbox element for the -DELETE request.
			            const rank_del   = document.createElement("input");
			            rank_del.type 	 = "checkbox";
			            rank_del.value 	 = "on";
			            rank_del.checked = true
			            rank_del.id 	 = rid.id.replace("-id", "-DELETE");
			            rank_del.name	 = rid.name.replace("-id", "-DELETE");		            
			            rank_del.style.display = 'none';
			            row.appendChild(rank_del);
			            
			            deleted_ranks++; 
		            }
		            
		            // Only request a deletion if the pid has a value (was not not added during this edit session)
		            if (pid.value) {
						// Add a hidden element for the -DELETE request.
		                const perf_del   = document.createElement("input");
		                perf_del.type 	 = "checkbox";
		                perf_del.value 	 = "on";
		                perf_del.checked = true;
		                perf_del.id 	 = pid.id.replace("-id", "-DELETE");
		                perf_del.name	 = pid.name.replace("-id", "-DELETE");
			            perf_del.style.display = 'none';
		                row.appendChild(perf_del);
		                
		                deleted_perfs++;
		            }
				}				
			}		
		}

		// We have to add the number of deleted forms to the TOTAL_FORMS field in the management form
		// or Django will ignore them (i.e. only process TOTAL_FORMS forms not these extra ones.
		updateManagementForms($$(id_indiv_div));

		// Remove the team play form completely before submitting
		if ($$(id_teams_div)) $$(id_teams_div).remove();	
	}	
}

// Re-configures the form for a new game if the game is changed (on an edit form).
function configureGame() {
    // Set some useful dervived globals
	game_min_teams = Math.max(game_min_players/game_max_players_per_team, 2);
	game_max_teams = Math.max(game_max_players/game_min_players_per_team, 2);	
	
	// Reads the global game options and ses the play mode as needed and limits the player counts as needed.
	const team_switch = $$(id_team_switch);
	
	// game_individual_play is true if the game supports individual play mode
	// game_team_play is true if the game supports team play mode
	// These are game properties.
	
	// If the game supports only one mode, force that mode. 
	if (game_individual_play && !game_team_play) {
		if (team_switch.checked) {
			team_switch.checked = false;
			switchMode();
		}

		const num_players = $$(id_num_players);
		if (num_players.value < game_min_players) num_players.value = game_min_players;  
		if (num_players.value > game_max_players) num_players.value = game_max_players;
		num_players.defaultValue = num_players.value; 
		num_players.setAttribute('min', game_min_players);
		num_players.setAttribute('max', game_max_players);	

		adjustTable(num_players);
		
		$$(id_teams_div).style.display = 'none';		
		$$(id_indiv_div).style.display = 'block';		
	} else if (game_team_play && !game_individual_play) {
		if (!team_switch.checked) {
			team_switch.checked = true;
			switchMode();
		}

		const num_teams = $$(id_num_teams);
		if (num_teams.value < game_min_teams) num_teams.value = game_min_teams;  
		if (num_teams.value > game_max_teams) num_teams.value = game_max_teams; 
		num_teams.defaultValue = num_teams.value; 
		num_teams.setAttribute('min', game_min_teams);
		num_teams.setAttribute('max', game_max_teams);
		
		adjustTable(num_teams);

		for (let i = 0; i < num_teams.value; i++) {
	    	const idTable = 'tblTeamsBody' + i;
	    	const Table = $$(idTable);
            const num_players = findChildByName(Table, name_num_team_players.replace(form_number,i));
			if (num_players.value < game_min_players_per_team) num_players.value = game_min_players_per_team;  
			if (num_players.value > game_max_players_per_team) num_players.value = game_max_players_per_team; 
			num_players.setAttribute('min', game_min_players_per_team);
			num_players.setAttribute('max', game_max_players_per_team);
			num_players.setAttribute('defaultValue', num_players.value); 
			
			adjustTable(num_players);
		}
		
		$$(id_indiv_div).style.display = 'none';
		$$(id_teams_div).style.display = 'block';		
	} 
	
	// Else do nothing, the form can stay in the mode its in (Individual or Team Play)
	
	// But in all cases disable the team switch if only one mode is available.
	team_switch.disabled = (!game_individual_play || !game_team_play); 	
}

// Event handler for a new game selection
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

// Event handler for new play mode selection (swapping from Individual to Team or vice versa) 
function switchMode(event) {
	const team_switch = $$(id_team_switch);
	
    if (team_switch.checked) {
    	// Switch from individual play to team play
    	const table_players = $$(id_tbl_players);
		const num_teams = $$(id_num_teams);	

		const session = convert_session_data_from(table_players);

		num_teams.value = session["rIDs"].length;
		num_teams.defaultValue = num_teams.value; 
    	
		const table_teams = adjustTable(num_teams, session);
		
		for (let t=0; t<num_teams.value; t++) {
	    	const real_name_num_team_players = name_num_team_players.replace(form_number,t);
	    	const id_table = 'tblTeamsBody' + t;
	    	const table_teams = $$(id_table);	    	
			const num_team_players = findChildByName(table_teams, real_name_num_team_players);
			
			adjustTable(num_team_players, session);
		}

		$$(id_indiv_div).style.display = 'none';
    	$$(id_teams_div).style.display = 'block';
    	
    	enableChildren($$(id_indiv_div), false);
    	enableChildren($$(id_teams_div), true);    	
    } else {
    	// Switch from team play to individual play
    	const table_teams = $$(id_tbl_teams);	
		const num_players = $$(id_num_players);

		const session = convert_session_data_from(table_teams);
		
		num_players.value = session["rIDs"].length;		
		num_players.defaultValue = num_players.value; 
		
		adjustTable(num_players, session);

    	$$(id_teams_div).style.display = 'none';
    	$$(id_indiv_div).style.display = 'block';
    	
    	enableChildren($$(id_teams_div), false);
    	enableChildren($$(id_indiv_div), true);
    }    
}

// table can be one of tblIndividualPlay or tblTeamPlay from the associated template
// Will extract from the widgets data to fill a session data dictionary
function convert_session_data_from(table){
	if (table.id == id_tbl_players) {
		// We look for
		//	one rank_id per player in widget name_rid
		// 	one rank per player in the widget with name_rank
		//	one performance id per player in widget name_pid
		//  one player id per player in widget name name_player
		//	one partial play weight per player in widget name_weight
		//
		// All names have an embedded form_number which is 0, 1, 2, 3 sequentially for each player on the form.
		//
		// The number of players is stored in id_num_players
		//
		// We will create one team per game_min_players_per_team,and fold rIDs together in the team rID
		// as an & separrated list. The last team if needed will accept the remainder.
		const rIDs = [];
		const ridRanks = {};
		const ridTeams = {}; 
		const tidTeamNames = {}; 
		const tidTeamPlayers = {}; 
		const plidPerformances = {};
		const plidWeights = {};
		
		const num_players = $$(id_num_players).value;
		const num_teams = Math.trunc(num_players / game_min_players_per_team);
		const ranks = [];
		for (let p=0; p<num_players; p++) {
			const rid 		= getWidget(table, name_rid, p);
			const pid 		= getWidget(table, name_pid, p);
			const rank 		= getWidget(table, name_rank, p);
			const player 	= getWidget(table, name_player, p);
			const weight 	= getWidget(table, name_weight, p);
			
			const t = Math.trunc(p / game_min_players_per_team);	
			const tID = id_prefix+t;
			tidTeamNames[tID] = "Team " + t;

			const rID = (isNaN(rid.value) ? id_prefix+p : rid.value);

			if (rIDs.length <= t) {
				// Then start the lists for each team
				rIDs.push(rID);
				tidTeamPlayers[tID] = [player.value];
				ranks[t] = rank.value;
			}
			else {
				// Add a player to the list
				rIDs[t] = rIDs[t] + "&" + rID;
				tidTeamPlayers[tID].push(player.value);
			}			
			
			const plID = player.value;
			plidPerformances[plID] = pid.value;
			plidWeights[plID] = weight.value;
		}

		for (let t=0; t< rIDs.length; t++) {
			const rID = rIDs[t];
			const tID = id_prefix+t;
			
			ridTeams[rID] = tID;
			ridRanks[rID] = ranks[t];
		}
		
		const Session = {'rIDs'			: rIDs, 			// Array of rank IDs
		 		 		 'Ranks'		: ridRanks,			// dict of ranks keyed on rID 
		 		 		 'Players'		: {},	    		// dict of player IDs keyed on rID 
		 		 		 'Teams'		: ridTeams, 		// dict of team IDs keyed on rID
		 		 		 'TeamNames'	: tidTeamNames, 	// dict of team names keyed on tID.
		 		 		 'TeamPlayers'	: tidTeamPlayers, 	// dict of team player lists keyed on tID with list of player IDs as value
		 		 		 'pIDs'			: plidPerformances, // dict of performance IDs keyed on player ID 
		 		 		 'Weights'		: plidWeights}		// dict of performance weights keyed on player ID

		return Session;		
	}
	else if (table.id = id_tbl_teams) {
		// We look for
		//	one rank_id per team in widget name_rid
		// 	one rank per team in the widget with name_rank
		//	one team name per team in the widget name_team_name
		//	one performance id per player in widget name_pid
		//  one player id per player in widget name name_player
		//	one partial play weight per player in widget name_weight
		//
		// The team properties have an embedded form_number which is 0, 1, 2, 3 sequentially for each team on the form.
		// The player properties have an embedded form_number which is of form t.p where t and p are 0, 1, 2, 3 sequentially
		// t being the team form number and p being the player form number inside of the team.
		//
		// The number of teams is stored in id_num_teams and the number of players in each team in name_num_team_players 
		// which has form_number in it of 0, 1, 2, 3 etc for each team.
		
		// Initialise the session data buckets
		let rIDs = [];
		let ridRanks = {};
		let ridPlayers = {}; 
		let plidPerformances = {};
		let plidWeights = {};
		
		const num_teams = $$(id_num_teams).value;
		for (let t=0; t<num_teams; t++) {
			// The rank widgets
			const rid 		= getWidget(table, name_rid, t);
			const rank 		= getWidget(table, name_rank, t);
			const team_name = getWidget(table, name_team_name, t);
			
			// The number of players in the team at this rank
			const real_name_num_team_players = name_num_team_players.replace(form_number,t);
			const num_team_players = findChildByName(table, real_name_num_team_players).value;			
			
			// Collect the player data from all the team members
			const rids = rid.value.split("&");    // rIDs may have been folded from a previos individual->team mode conversion (above) 
			const pids = [];
			const players = [];
			const weights = [];
			for (let p=0; p<num_team_players; p++) {
				const form_num  = t+"."+p;
				const pid 		= getWidget(table, name_pid, form_num);
				const player 	= getWidget(table, name_player, form_num);
				const weight 	= getWidget(table, name_weight, form_num);

				pids.push(pid.value);
				players.push(player.value);
				weights.push(weight.value);
				
				// The first player in each team gets the teams rank ID
				// subsequent players get a rank ID of id_prefix+form_number
				// which is a placeholder only, and on submission we have to 
				// blank that out so that a standard Django formset save knows 
				// to generate a new rank ID for that player. 
				//
				// The rank IDs of the teams can be recycled for use by	the first 
				// player on each team.
				rids.push((p<rids.length) ? rids[p] : id_prefix+form_num);
			}
			
			// Now push all the players into the session data buckets
			for (let p=0; p<num_team_players; p++) {
				const rid = rids[p];
				rIDs.push(rid);
				ridRanks[rid] = rank.value;
				
				const plid =  players[p];
				ridPlayers[rid] = plid;
				
				plidPerformances[plid] = pids[p];
				plidWeights[plid] = weights[p];				
			}			
		}
		
		const Session = {'rIDs'			: rIDs, 			// Array of rank IDs
				 		 'Ranks'		: ridRanks,			// dict of ranks keyed on rID 
				 		 'Players'		: ridPlayers,	    // dict of player IDs keyed on rID 
				 		 'Teams'		: {}, 				// dict of team IDs keyed on rID
				 		 'TeamNames'	: {}, 				// dict of team names keyed on tID.
				 		 'TeamPlayers'	: {}, 				// dict of team player lists keyed on tID with list of player IDs as value
				 		 'pIDs'			: plidPerformances, // dict of performance IDs keyed on player ID 
				 		 'Weights'		: plidWeights}		// dict of performance weights keyed on player ID
	
		return Session;
	}
}

// Event handler for a the row count changes, can respond to three types of change:
// In Individual Play Mode:
// 		Number of players
// In Team Play Mode:
//		Number of Teams
//		Number of Players on a given team
function OnRowcountChange(event) {
	const num_box = event.target;
	
	const Table = adjustTable(num_box);

	// TODO: Diagnose - This fails. Want to add 2 players to newly added teams. How?
	if (event.target.id === id_num_teams) {
		for (var i = 0; i < event.target.value; i++) {
		    var boxNum = findChildByName(Table.parentNode, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.

		    adjustTable(boxNum);
		}
	}
}

// Event handler for change of a selected player
// In Individual Play Mode, the player is identified in both a Rank object and a Performance Object. 
// And so the form has to contain two widgets:
//		related_forms.Rank.player
//		related_forms.Performance.player
// One should be display the other hidden. This event handler attached to the displayed, copies the selected
// player ID to the hidden one. This ensures that both the Rank and Performance update the relevant Rank and 
// Performance database objects on a standard Django formset save. 
function OnPlayerChange(event) {
	const id = event.target.id
	let player_copy_id = id.includes(performance_prefix) 
					   ? event.target.id.replace(performance_prefix, rank_prefix)
					   : id.includes(rank_prefix)
					   ? event.target.id.replace(rank_prefix, performance_prefix):
					   null;
					   
	if (player_copy_id != null) {
		const player_copy = $$(player_copy_id);
		player_copy.value = event.target.value;
	}
}

// Event handler for the Team Detail visibility checkbox. 
// Hides or shows the the TeamPlayersTable
function showhideTeamPlayers(event) {
    const checked = event.target.checked;
    const rowTeam = getParent(event.target,"TR");
    const numTeam = getEntryId(rowTeam.id);
    const idTeamPlayers = "tblTeamPlayersTable" + numTeam;
    const tblTeamPlayers = $$(idTeamPlayers);

    if (tblTeamPlayers != null) tblTeamPlayers.style.display = (checked ? 'block' : 'none');
}

// Event handler for showing and hiding the trasg
function showhideTrash(event) {
    const checked = event.target.checked;
	if (checked) $(".trash").show(); else $(".trash").hide(); 
}

// There are managment forms for both Rank and Performance that must be included in the template.
// a la:
//			{{ related_forms.Rank.management_form }}
//			{{ related_forms.Performance.management_form }}
// and these contain hidden fields with known names (defined in the header above).
///
// Given an embracing div element, this will find the relevant management form fields 
// and update them. Notably the TOTAL values to reflect the number of Ranks and Performances
// respectively that will be submitted.
//
// If the TOTAL is less than the INITIAL then Ranks and/or Performances were removed on an
// edit and we need to submit -DELETE fields to ensure those records are destroyed in the 
// database by the Django form saver. 
function updateManagementForms(div) {
    // Keep the Django Management form totals up to date.
	//
    // When this is an "add" form we update the INITIAL management form values as well.
    // When it's an "edit" form these will be set already by Django to the correct counts
	//
    // When it's an "add" form Django sets them to the count of objects in the database (rather than 0)
    // But as we are creating an initial form with Javascript we MUST update the INITIAL values too to 
	// be 0 for Django to read these as creations and generate primary keys
	//
	// INITIAL is very relevant to "edit" formas as well, as when TOTAL is below INITIAL we need to
	// destroy Rank or Perfomance objects (we've removed competitors from the ranking). These must
	// be flagged with a -DELETE element.
	
    const rinit  = findChildByName(div, name_rinit);
    const pinit  = findChildByName(div, name_pinit);
    const tinit  = findChildByName(div, name_tinit);
    const rtotal = findChildByName(div, name_rtotal);
    const ptotal = findChildByName(div, name_ptotal);
    const ttotal = findChildByName(div, name_ttotal);

    // On an add operation, rinit and pinit come in oddly as the total number 
    // of Rank and Performance items respectively in the database.
    // Django needs them to be 0 to understand that the Ranks and Performances 
    // submitted are new and need new primary keys
	if (operation === "add") {
		rinit.value = 0;
		pinit.value = 0;
		if (tinit) tinit.value = 0;  // tinit is undefined when in individual mode
	}

	// Find all the -DELETE requests that exist, each one of these represents a form in the formset 
	// and so we must add their count to the number declared in $$(id_num_players)
    const rdels = div.querySelectorAll("[id^='"+id_prefix+rank_prefix+"'][id$='-DELETE']").length;
    const pdels = div.querySelectorAll("[id^='"+id_prefix+performance_prefix+"'][id$='-DELETE']").length;
    const tdels = div.querySelectorAll("[id^='"+id_prefix+team_prefix+"'][id$='-id']").length;	
	
    if (div.id === id_indiv_div) {
    	const num_players = Number($$(id_num_players).value);
    	rtotal.value = num_players + rdels;
    	ptotal.value = num_players + pdels;
    } else if (div.id === id_teams_div) {
    	
    	
    	const num_teams = Number($$(id_num_teams).value);
    	rtotal.value = num_teams + rdels;

    	let p = 0;
		for (let t = 0; t < num_teams; t++) {
	    	const id_table = 'tblTeamsBody' + t;
	    	const table = $$(id_table);
            const box_num_players = findChildByName(table, name_num_team_players.replace(form_number,t));
    		p += Number(box_num_players.value);
        }
		ptotal.value = p + pdels;
		
    	ttotal.value = num_teams + tdels;
    }
}

// Given a template HTML table element, will: 
// On a first call for that template, create a 
// new table from it adding:
// 		a header from a template header in the template table and 
// 		rows from a template row in the template table
// and place the table in a provided element.
// On subsequent calls for that template will use the table already 
// created and adjust it as needed.
//
// This is generic as it is used for an Individual Play mode and
// a Team play mode each with its own template. Only the 
// relevant one will be visible on a given form, based on the
// the nominated play mode (Team_pay - True or False)
//
// Template structures expected are:
//	For Individual Play mode:
//		table: templatePlayersTable				The table of Player rankings
//			tr: templatePlayersHeader			A header row
//			tr: templatePlayersBody				One of these rows per player for Ranks and Performances
//	For Team Play mode:
//		table: templateTeamsTable					The table of Team rankings
//			tr: templateTeamsHeader					A header row
//			tr: templateTeamsBody					One of these rows per team, for Ranks
//			tr: templateTeamsDetail					One of these rows per team, contains the TeamsDetailCell 
//				td: templateTeamsDetailCell			the cell to contain a table of one row row per player for Performances
//					table: templateTeamPlayersTable 	The table of team players
//						tr: templateTeamPlayersHeader	A header row
//						tr: templateTeamPlayersBody		One of these rows per player in the team
function RenderTable(template, entries, placein, entry_number, session) {
    // The Number of players in a team is a special case quite distinct
    // from the number of teams or number of players in a game. Primarily
    // because it lives in particular row of the parent table there being
    // a number of players for each team. We'll make a number of decisions 
    // on this basis down the track. 
    const is_players 		= (template.id === "templatePlayersTable");      
    const is_teams 			= (template.id === "templateTeamsTable");      
    const is_teamplayers 	= (template.id === "templateTeamPlayersTable");      

    // Get the ID of the table that we will render (based on the template) 
	const idTable = template.id.replace("template", "tbl") + entry_number;	

    // Get the ID of a hidden parallel trash table that we dump 
    // deleted rows into and restore them from.
	const idTrash = idTable.replace("tbl", "trash");
    
    // Is it a new table (first call for this template) or does it already exist (subsequent calls) 
    const is_newtable = ($$(idTable) == null);
    const is_newtrash = ($$(idTrash) == null);

    // Create the table if needed else use the one we have.
    const table = is_newtable ? document.createElement('table') : $$(idTable);
    const trash = is_newtrash ? document.createElement('table') : $$(idTrash);
    
    // If it's a new table we need to set it up and place it where it belongs
    if (is_newtable) {
        table.id = idTable;
        table.className = template.className;
        table.style = template.style;        
        
        const trash_header = document.createElement('span');
        trash_header.classList.add(template.className);
        trash_header.classList.add('trash');
        trash_header.style = template.style;
        trash_header.innerHTML = "Trash:";                
        
        trash.id = idTrash;
        trash.classList.add(template.className);
        trash.classList.add('trash');
        trash.style = template.style;

        placein.appendChild(table);
        placein.appendChild(trash_header);
        placein.appendChild(trash);
    }
   
    // "entries" is the number typed into the Number of Players/Teams box,
    //		for Number of players: we need 1 row per player
    //		for Number of teams: we need 2 rows per team, 
    //			one for the team rank, name, and number of players (in the team) 
    //			one for the details (player list).
    // In both cases we need a header row!.
    var rowsNeeded = (is_teams ? 2*entries : entries) + 1;
    var rowsPresent = table.rows.length;

    if (rowsNeeded < rowsPresent) {
    	// Move the excess rows to the trash (whence we can fetch them again if needed)
    	// Never remove them all though. 0 entries not supported. The trash is FILO 
    	// queue in that we append entries as we remove them and then pull them off 
    	// the top again when needed. 
        if (entries > 1)
	        for (let i = 0; i < (rowsPresent - rowsNeeded); i++) {
	        	const last_row = table.rows[table.rows.length - 1];
	        	trash.appendChild(last_row);

	        	if (is_teams) {
		        	const last_row = table.rows[table.rows.length - 1];
		        	trash.appendChild(last_row);	        		
	        	}	        	
	        }
    } else if (rowsNeeded > rowsPresent) {
    	// Add the missing rows, fetching them from trash if there else creating them
    	
    	// Every Table template is expected to have a Header and Body template within it 
        const trh = $$(template.id.replace("Table", "Header"));      // The template table header row
        const trb = $$(template.id.replace("Table", "Body"));		 // The template table body row

        // Build a header row first if it doesn't already exist!
        if (rowsPresent == 0) {
            const TRH = trh.cloneNode(true);
            TRH.id = trh.id.replace("template", "tbl");
            TRH.className = trh.className;
            TRH.style = trh.style;

            table.appendChild(TRH);
            rowsNeeded--;
        }

		// Now lets work out how many steps of "adding" rows we need
        // On a teams table we add them in pairs so need half the steps (TeamsBody and TeamsDetail) 
        const steps = is_teams ? (rowsNeeded - rowsPresent) / 2 : rowsNeeded - rowsPresent;

        for (let i = 0; i < steps; i++) {
            // Build an entry ID, which is just an integer representing the row for
            // either Players in Individual Play mode or Teams in Team Play mode. But for
            // Players in Team Play mode it will be a composit number of form "team.player"
        	const body_rows = rowsPresent > 0 ? rowsPresent - 1 : 0;
        	const entry_id = (is_teamplayers ? (entry_number + '.') : 0) 
        				   + ((is_teams ? body_rows/2 : body_rows) + i);            

        	// If is_teams we need to pop two items off trash, else only one
        	const have_trash = trash.rows.length >= (is_teams ? 2 : 1);        	
        	
        	if (have_trash) {
	        	const last_row = trash.rows[trash.rows.length - 1];
	        	table.appendChild(last_row);

	        	if (is_teams) {
		        	const last_row = trash.rows[trash.rows.length - 1];
		        	table.appendChild(last_row);
	        	}        		
        	} else {
	        	// Get the Body TR element and set it up
	            const TRB = trb.cloneNode(true);
	            TRB.id = trb.id.replace("template", "tbl") + entry_id;
	            TRB.className = trb.className;
	            TRB.style = trb.style;
	
	            // Get the widgets in TRB. The template must define these widgets
	            // in a row of the body. We fetch them here and fix them up
	            const rid 			= fixWidget(TRB, name_rid, entry_id);        // This is the ID of the rank entry in the database. Needed when editing sessions (and the ranks associated with them)
	            const pid 			= fixWidget(TRB, name_pid, entry_id);        // This is the ID of the performance entry in the database. Needed when editing sessions (and the ranks associated with them)
	            const rank 			= fixWidget(TRB, name_rank, entry_id);       // This is the rank itself, a dango field for generic processing, but with a default value added when created here as well
	            const player 		= fixWidget(TRB, name_player, entry_id);     // This is the name/id of the player with that rank, a dango field for generic processing
	            const player_copy 	= fixWidget(TRB, name_player_copy, entry_id);// This is a copy of the player we need to keep of player (see header for details)
	            const weight 		= fixWidget(TRB, name_weight, entry_id);     // This is the partial play weighting, a dango field for generic processing
	            const tid 			= fixWidget(TRB, name_tid, entry_id);        // This is the team ID if we're editing a team session
	            const teamname 		= fixWidget(TRB, name_team_name, entry_id);  // This is the name of the team. Optional in the database and it an stay a local field for specific (non-generic) processing when submitted.
	
	            // Select the values we'll use for those widgets
	            const rids 			= ("rIDs" in session) 		? session["rIDs"] 			: []; 
	            const ranks 		= ("Ranks" in session) 		? session["Ranks"] 			: {}; 
	            const players 		= ("Players" in session) 	? session["Players"] 		: {}; 
	            const teams 		= ("Teams" in session) 		? session["Teams"] 			: {}; 
	            const teamnames 	= ("TeamNames" in session) 	? session["TeamNames"] 		: []; 
	            const teamplayers 	= ("TeamPlayers" in session)? session["TeamPlayers"] 	: {}; 
	            const pids 			= ("pIDs" in session) 		? session["pIDs"] 			: {}; 
	            const weights 		= ("Weights" in session) 	? session["Weights"] 		: {}; 
	            
	            if (is_players) {
	                rid.value 	 = entry_id < rids.length   ? rids[entry_id] 	 	: "";
	                rank.value 	 = rid.value in ranks 	 	? ranks[rid.value] 	 	: entry_id+1;
	                player.value = rid.value in players		? players[rid.value] 	: "";	                               
	                pid.value 	 = player.value in pids 	? pids[player.value] 	: "";
 	                weight.value = player.value in weights 	? weights[player.value] : 1;	                               
	                player_copy.value = player.value;
	            } else if (is_teams) {
	                const num_players = fixWidget(TRB, name_num_team_players, entry_id); 

	                rid.value 	 	= entry_id < rids.length ? rids[entry_id] 	: "";
	                rank.value 	 	= rid.value in ranks 	 ? ranks[rid.value] 	: entry_id+1;
	                tid.value 	 	= rid.value in teams 	 ? teams[rid.value] 	: "";	                
	                teamname.value 	= rid.value in teamnames ? teamnames[rid.value] : "Team " + (entry_id+1);

	                const tID = tid.value;
	                
	                num_players.value = (tID in teamplayers && entry_id < teamplayers[tID].length) ? teamplayers[tID][entry_id].length : game_min_teams;
	    			num_players.defaultValue = num_players.value;   			
	            } else if (is_teamplayers) {
	                const rownum_Team 	  	= getPart(1, entry_id);
	                const rownum_TeamPlayer = getPart(2, entry_id);
	                
	                // Find Player ID first so we can use it to find the index into the Weights and pID lists
	                const rID = rownum_Team < rids.length ? rids[rownum_Team] : undefined;
	                const tID = rID in teams ? teams[rID] : undefined;
	                player.value = tID in teamplayers ? teamplayers[tID][rownum_TeamPlayer] : ""; 	                	
	                
 	                weight.value = player.value in weights 	? weights[player.value] : 1;	                               
	                pid.value 	 = player.value in pids 	? pids[player.value] 	: "";
	            } 
	
	            enableChildren(TRB, true);
	
	            table.appendChild(TRB);
	
	            // Add the second row, the (empty) Detail row if needed for added Teams
	            if (is_teams) {
	                const trd = $$(template.id.replace("Table", "Detail"));  
	                const TRD = trd.cloneNode(true);
	                TRD.id = trd.id.replace("template", "tbl") + entry_id;
	
	                const TCDid = trd.id.replace("template", "tbl") + "Cell" + entry_id;
	                TRD.children[0].id = TCDid;
	
	                table.appendChild(TRD);
	            }
        	}
        }
    }

    // Update the Django Management forms
    updateManagementForms(getParent(table, 'DIV'));

    // Return the table that was drawn
    return(table);
}

// Given a HTML with a value will adjust the associated table
// to the number of rows specified in that value.
//
// Is called in three contexts:
//
// In Individual Play mode:
//		When the number of players in the game is altered
// In Team Play mode:
//		When the number of teams in the game is altered
//		When the number of players in a team is altered
//
// We assume that the the value holding element is in a table 
// which also holds a template that we can use to render the 
// table with. A map is defined from holding table to template
// table.
//
// element should be one of:
// 		NumPlayers
//		NumTeams
//      Team-__prefix__-num_players
function adjustTable(element, session) {
	// Find the table the value holding element is a member of:
    const td = getParent(element, "TD");
    const tr = getParent(td, "TR");
    const tableControl = getParent(tr, "TABLE");    
    
    // Determine which session data to use (if none supplied use the Global set
    if (!session) session = Session;
    
    // Define a map from the holding table to the contained table 
    // that we want to adjust
    const mapTemplate = {
    		tblIndividualPlay:	"templatePlayersTable", 
    		tblTeamPlay:	 	"templateTeamsTable", 
    		tblTeamsTable: 		"templateTeamPlayersTable"
    };

    // Now fetch a template id from the map. 
    const idTemplate = mapTemplate[tableControl.id];

    // Fetch the the template
    const template = $$(idTemplate);

    // The Number of players in a team is a special case quite distinct
    // from the number of teams or number of players in a game. Primarily
    // because it lives in particular row of the parent table there being
    // a number of players for each team. We'll make a number of decisions 
    // on this basis down the track. 
    const is_players 		= (template.id === "templatePlayersTable");      
    const is_teams 			= (template.id === "templateTeamsTable");      
    const is_teamplayers 	= (template.id === "templateTeamPlayersTable");      
    
    // The Number of players in a team is a special case quite distinct
    // from the number of teams or number of players in a game. 
    let idTable, FormNumber, placein;
    if (is_teamplayers) {
        placein = $$(tr.id.replace("Body","DetailCell"));
        idTable = idTemplate.replace("template","tbl") + getFormNumber(element.name);
    } else {
        placein = template.parentNode;
        idTable = idTemplate.replace("template","tbl");
    }

    // Fetch the the table
    const table = $$(idTable);

    // If the value is an integer (string of digits) then process it
    if (element.value.match(/^\d+$/)) {   	
    	// The minimum and maximum number of players  or teams are game properties (globally available) 
        const minEntries = is_teamplayers ? game_min_players_per_team : is_teams ? game_min_teams : game_min_players;	
        const maxEntries = is_teamplayers ? game_max_players_per_team : is_teams ? game_max_teams : game_max_players;	
        
        // The number of teams or players being requested, with a minimum and maximum enforced
        const num = Number(element.value);
        const numEntries = num < minEntries ? minEntries : num > maxEntries ? maxEntries : num;	

        // If the value was changed (exceeeded bounds) change it back! 
        if (numEntries != num) element.value = numEntries	
        
        // Render the table with the new number of entries, and place it in the nominated element
        RenderTable(template, numEntries, placein, getEntryId(tr.id), session);

        // If we're altering the number of players on a team display the Team players
        if (is_teamplayers) {
        	const chkShowTeamPlayers = findChildByName(tr,'ShowTeamPlayers');
        	chkShowTeamPlayers.checked = true;
        }
    } else {
        element.value = element.defaultValue;
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
function getWidget(inside, name, entry_id) {
	return entry_id != undefined ? findChildByName(inside, name.replace(form_number, entry_id)) : findChildByName(inside, name);
}

// Get the Django widget with a give name inside a given element, and update it with the give row id.
function fixWidget(inside, name, entry_id, new_entry_id) {
	const widget = new_entry_id == undefined 
				 ? findChildByName(inside, name)
				 : findChildByName(inside, name.replace(form_number, entry_id));

	if (widget) {
		const from 	= new_entry_id == undefined ? form_number 	: entry_id;
		const to   	= new_entry_id == undefined ? entry_id 		: new_entry_id;
		widget.id   = widget.id.replace(from, to);
		widget.name = widget.name.replace(from, to)
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
function getEntryId(of) {
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
//  return document.getElementById(id);
//  or using jQuery:
    return $('#'+	id)[0];
}
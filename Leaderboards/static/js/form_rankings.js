const debug = true;

// This is taken from: https://stackoverflow.com/a/54734354/4002633
// it doesn't work alas if inclided as a separate <script> tage in the sourcig file.
// It's formalised here: https://github.com/colxi/required-parameters-js
Object.defineProperty( window , 'required'  , {
  get : ()=>{
    let err     = new Error('');
    let trace   = err.stack.split('\n');
    let msg     = '';
    for(let i=2;i<trace.length;i++)  msg+=trace[i]+'\n';
    throw 'Error : Missing required parameter\n' + msg;
  },
  configurable : false
});

// A little utitility function based on:
// https://www.tutorialspoint.com/how-to-sort-an-object-in-ascending-order-by-the-value-of-a-key-in-javascript
// https://stackoverflow.com/a/11352763/4002633
// Have to love Javascript for its simplicty, not!
const sortObject = (obj, descending) => {
   if (descending === undefined) descending = false;
   const sorter = (a, b) => {return descending ? obj[b] - obj[a] : obj[a] - obj[b];};
   const keys = Object.keys(obj);
   keys.sort(sorter);
   const res = [];
   keys.forEach(key => {res.push(key)});
   return res;
};

// Load the session data (function is defined in the loading html file because it needs
// to use on Django template tags to get input from Django with which to populate the
// Sessions structure).
const Session = get_session_data();

// Build a Session object (dict) from supplied data.
//
// A Session is one sitting of players or teams of players at a table playing a game, with an outcome (ranks or scores).
//
// Four data sources in three contexts are currently used to build this and this function serves to centralise the
// construction ensuring the same thing is built regardless of context or source and so the supplier knows what to
// provide and no-one gets left behind (if the structure changes).
//
// The three contexts (and four data sources) are:
//
// 1. The Django template engine (appearing as literal definitons herein)
// 2. The Django form data (arrriving in form.data) whe Django reloads the form after an error
// 3. When the form herein changes its presentation mode betwee a Team play game and an Individual play game and back
//      a. When switching to team play mode the source is an existing individual form
//      b. When switching to individual mode the scource is an existing team form
//      These forms take such a Session object to populate the forms they build, So when moving to the other form
//      the contents are delivered bi the same (input) Session structure.
//
// By forcing required paramters using:
//		https://github.com/colxi/required-parameters-js
// callers failing to supply data can easily be identified when debugging (throwing console errrors)
// (a shame standard JS doesn't support this well)
//
// The key is r, p or t for rank ID, performance ID or team ID
function session_dict(
		team_play	   = requires,  // Boolean flagging the play mode
		// Rank ID (rID) indexed items
		rIDs           = required,  // Array of rank IDs
		ridRanks       = required,	// dict of ranks keyed on rID
		ridScores      = required,	// dict of scores keyed on rID
		ridPlayers     = required,	// dict of player IDs keyed on rID
		ridTeams       = required, 	// dict of team IDs keyed on rID
		// Team ID (tID) indexed items
		tidTeamNames   = required, 	// dict of team names keyed on tID.
		tidTeamPlayers = required, 	// dict of team player lists keyed on tID with list of player IDs as value
		// Performance ID (pID) indexed items
		pIDs           = required,	// Array of performance IDs
		pidPlayers     = required, 	// dict of player IDs keyed on pID
		pidScores      = required, 	// dict of performance scores keyed on pID
		pidWeights     = required	// dict of performance weights keyed on pID
	) {

	// The rid and pid arrays are not premised to align
	// in matter of fact the server may supply session data with rids sorted by rank and pids sorted by player say
	// To wit, we want and extra dict that maps pid to rid.
	// In that direction as it is 1 to 1 in individual mode an n to 1 in team mode (pid to rid)
	let pidRIDs = {};

	if (team_play) {
		for (let pid of pIDs) {
			const player = pidPlayers[pid];
			const tid = Object.keys(tidTeamPlayers).find(tid => tidTeamPlayers[tid].includes(player));
			const rid = Object.keys(ridTeams).find(rid => ridTeams[rid] === tid);
			pidRIDs[pid] = rid;
		}
	} else {
		for (let pid of pIDs) {
			const player = pidPlayers[pid];
			const rid = Object.keys(ridPlayers).find(rid => ridPlayers[rid] === player);
			pidRIDs[pid] = rid;
		}
	}

	// The key is r, p or t for rank ID, performance ID or team ID
	// If this changes make sure to update the function collect_session_data_from as well which produces the same structure
	// The "provided" flag indicates that this session was provided because this is an edit form or an add form that was submitted and bounced with errors
	// It serves to indicate that we have session data (ranks, scores, players) and not placeholders which are used at times.
	const Session = {'provided'		: false,	        // A flag to tell if Session Data was provided (set by the provider/caller defaults false)
					 'team_play'    : team_play,	    // boolean indicating play mode
					 // Rank ID (rID) keyed dicts
					 'rIDs'			: rIDs, 			// Array of rank IDs
					 'rRanks'		: ridRanks,			// dict of ranks keyed on rID
					 'rScores'		: ridScores,		// dict of scores keyed on rID
					 'rPlayers'		: ridPlayers,	    // dict of player IDs keyed on rID
					 'rTeams'		: ridTeams, 		// dict of team IDs keyed on rID
					 // Team ID (tID) keyed dicts
					 'tTeamNames'	: tidTeamNames, 	// dict of team names keyed on tID.
					 'tTeamPlayers'	: tidTeamPlayers, 	// dict of team player lists keyed on tID with list of player IDs as value
					 // Performance ID (pID) keyed dicts
					 'pIDs'			: pIDs,				// Array of performance IDs
					 'pPlayers'		: pidPlayers, 		// dict of player IDs keyed on pID
					 'pScores'		: pidScores, 		// dict of performance scores keyed on pID
					 'pWeights'		: pidWeights,		// dict of performance weights keyed on pID
					 // A connector between rid and pid lists
					 'pRIDs'		: pidRIDs};

	return Session;
}

// Global flags for managing rank and score columns
// a call to showhideRankScoreColumns() acts on these globals.
let show_rank_scores = false;	// The rank scores column
let show_perf_scores = false;	// The performance scores column
let show_tiebreakers = false;	//  Show the rank column to break rank score ties

if (Session.team_play) {
	show_rank_scores = game_scoring.includes("TEAM");
	show_perf_scores = game_scoring.includes("INDIVIDUAL");
} else {
	show_rank_scores = game_scoring.includes("INDIVIDUAL");
	show_perf_scores = false;
}
// A global flag that request all ranks and scores be visible for debugging.
let debug_ranks_and_scores = false;

/*
	Session is the key data structure for communicating a session between Django and this form and for
	managing form alterations (specifically play mode switches). It's useful therefore to see a sample
	of the two play modes.

	Unknown IDs (Rank, Player, Team, Performance) will carry a string of form "id_n" where n is 0, 1, 2 ...
	That being a sign that the id is unknown (this data not saved yet and given a database ID)
*/


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

// Some field query selectors (used with .querySelectorAll() to find all the respective ID elements)
const qs_tids 			  = `[id^='${id_prefix}${team_prefix}'][id$='-id']`;
const qs_rids 			  = `[id^='${id_prefix}${rank_prefix}'][id$='-id']`;
const qs_pids 			  = `[id^='${id_prefix}${performance_prefix}'][id$='-id']`;

const qs_tdels 			  = `[id^='${id_prefix}${team_prefix}'][id$='-DELETE']`;
const qs_rdels 			  = `[id^='${id_prefix}${rank_prefix}'][id$='-DELETE']`;
const qs_pdels 			  = `[id^='${id_prefix}${performance_prefix}'][id$='-DELETE']`;

const qs_ranks 			  = `[id^='${id_prefix}${rank_prefix}'][id$='-rank']`;
const qs_rscores 		  = `[id^='${id_prefix}${rank_prefix}'][id$='-score']`;
const qs_pscores 		  = `[id^='${id_prefix}${performance_prefix}'][id$='-score']`;

const qs_pplayers 		  = `[id^='${id_prefix}${performance_prefix}'][id$='-player']`;
const qs_rplayers 		  = `[id^='${id_prefix}${rank_prefix}'][id$='-player']`;

//The Django management form fields we need to keep up to date reflecting the number of forms in the formset if we want Django to save them for us
const name_rinit     	  = rank_prefix + "INITIAL_FORMS";
const name_pinit     	  = performance_prefix + 'INITIAL_FORMS';
const name_tinit     	  = team_prefix + 'INITIAL_FORMS';
const name_rtotal     	  = rank_prefix + "TOTAL_FORMS";
const name_ptotal     	  = performance_prefix + 'TOTAL_FORMS';
const name_ttotal     	  = team_prefix + 'TOTAL_FORMS';

const id_rinit     	  	  = id_prefix + name_rinit;
const id_pinit     	  	  = id_prefix + name_pinit;
const id_tinit     	  	  = id_prefix + name_tinit;
const id_rtotal     	  = id_prefix + name_rtotal;
const id_ptotal     	  = id_prefix + name_ptotal;
const id_ttotal     	  = id_prefix + name_ttotal;

// Actual model fields
const name_rank   		  = rank_prefix + form_number + '-rank';                            // Ranking (1st, 2nd, 3rd)
const name_rscore 		  = rank_prefix + form_number + '-score'; 	                        // In game score (int)
const name_pscore 		  = performance_prefix + form_number + '-score'; 	                // In game score (int)
const name_player     	  = performance_prefix + form_number + '-player';	                // Player name/id in the Performance object (and the the selector)
const name_player_copy    = rank_prefix + form_number + '-player';	                        // Player name/id in the Rank object in individual play mode (copied from name_player on submit)
const name_weight 		  = performance_prefix + form_number + '-partial_play_weighting'; 	// Partial play weighting (0-1)

const id_rank 		      = id_prefix + name_rank;
const id_rscore 		  = id_prefix + name_rscore;
const id_pscore 		  = id_prefix + name_pscore;
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
let   id_visbl_div 		  = undefined;													// The visible (in use) div

const id_num_players	   = "NumPlayers";												// ID of the field that contains the number of players (in in Individual Play mode)
const id_num_teams		   = "NumTeams";												// ID of the field that contains the number of teams (in in Team Play mode)
const id_show_tie_breakers = "ShowTieBreakers";											// ID of the checkbox for display tie breakers

const id_tbl_players 	  = "tblPlayersTable";											// ID of the table that contains the players (in in Individual Play mode)
const id_tbl_teams 		  = "tblTeamsTable";											// ID of the table that contains the teams (in in Team Play mode)
let   id_tbl_visbl 		  = undefined;													// The visible (in use) table

const id_team_switch  	  = id_prefix + 'team_play';								 	// The checkbox used to switch between Individual play mode and Team play mode


// an enum for types of table we'll support so that type specific actions
// can be taken by generic routines and table builders and manipulators.
const TableType 		  = Object.freeze({"Players":1, "Teams":2, "TeamPlayers":3});

// If the default displayed game has no values for these presume sesnible individual play defaults
if (game_min_players_per_team == 0) game_min_players_per_team = 1;
if (game_max_players_per_team == 0) game_max_players_per_team = 1;

// Define some neat globals for the default displayed game
let game_min_teams = Math.max(game_min_players/game_max_players_per_team, 2);
let game_max_teams = Math.max(game_max_players/game_min_players_per_team, 2);

// Add event listeners to initialize the form and to tidy it on submit
document.addEventListener('load', OnLoad, true);
document.addEventListener('submit', OnSubmit, true);

function OnLoad(event) {
	// Bind a listener to the team switch (so the form can adapt to the selected play mode)
	const team_switch = $$(id_team_switch);
	team_switch.addEventListener('click', switchMode)

	// Add a listener to the game selector (so that the form can adapt to the properties of the newly selected game)
	const game_selector = $("#"+id_prefix+"game");
	game_selector.on("change", switchGame);

	// DAL is flakey with the above change event handle. While sorting this I need a way to
	// manually invoke it so we add a button beside it.
	//	const target = "$('#" + game_selector[0].id + "')[0]";
	//	const button = `<button type="button" class="tooltip" id="btnLoad" onclick="${target}.dispatchEvent(new Event('change'));" style="margin-left: 1ch; bottom:-2px;">
	//					<img src="${reload_icon}"  class="img_button" style="height: 18px;">
	//					<span class="tooltiptext">Switch game</span>
	//				    </button>`;
	//	game_selector.after(button);

	// We have Session data if it's an edit operation or if it's an add operation that is being rerendered (with feedback).
	if (Session.provided) {
		if (Session.team_play) {
			showDiv("teams");

			// Constrain the supplied data to expected bounds
			let num_teams = Session["rIDs"].length; // one rank per team
			if (num_teams < game_min_teams) num_teams = game_min_teams;
			if (num_teams > game_max_teams) num_teams = game_max_teams;
			const elem_num_teams = $$(id_num_teams);
			elem_num_teams.value = num_teams;
	    	elem_num_teams.tabIndex = 1;

			// This will create the teams table with a header row and 2 rows per team (body and details).
			adjustTable(elem_num_teams);

			// For each team build the Team players table.
			// which goes on the details row of the teams table just created, in the teams detail cell.
			for (let i = 0; i < num_teams; i++) {
				const rID = Session["rIDs"][i];
				const tID = Session["rTeams"][rID];
				let num_players = Session["tTeamPlayers"][tID].length;
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
			showDiv("indiv");

			// Constrain the supplied data to expected bounds
			const min_players = game_min_players;
			const max_players = game_max_players;
			let num_players = Session["rIDs"].length; // one rank per player
			if (num_players < min_players) num_players = min_players;
			if (num_players > max_players) num_players = max_players;

			const elem_num_players = $$(id_num_players);
	    	elem_num_players.value = num_players;
	    	elem_num_players.defaultValue = num_players;
	    	elem_num_players.tabIndex = 1;

	        adjustTable(elem_num_players);
		}
	} else
		// Make sure the game is properly configured
		configureGame();

	// If an illegal game mode is loaded, or both game modes are supported the team_switch is enabled
	const lock = !( (team_switch.checked && !game_team_play)
				|| (!team_switch.checked && !game_individual_play)
				|| (game_individual_play && game_team_play)
				);

	team_switch.disabled = lock;

	manage_rank_ties();
}

function disable_ranks_scores_as_needed(div) {
	// A DRY function.
	// Rank/Score simplification. Submit only the ranks or scores visible to the
	// user while editing. The hidden fields are disabled (not submitted)
	// In particular this prevents and rank reconciliation errors if the client
	// has lapesd in the task fo rank reconiliation. Rank reconciliation is the
	// process of ensuring that ransk, rank scores and performance scores are
	// all in agreement - produce the same ranking (which takes account of the game
	// scoring method). Client side we do it here with reconcile_ranks(), but it
	// if we slip up at all, it's best to keep submission simple and let server side
	// infer ranks from the visible ranking elements.
	if (show_rank_scores && ! show_tiebreakers)
		for (rank of div.querySelectorAll(qs_ranks)) rank.disabled=true;
	if (!show_rank_scores)
		for (rscore of div.querySelectorAll(qs_rscores)) rscore.disabled=true;
	if (!show_perf_scores)
		for (pscore of div.querySelectorAll(qs_pscores)) pscore.disabled=true;
}

function submission_debug(div) {
	// A DRY function.
	// tids are of interest only because we may have injected some DLEET requests if a teams form
	// was loaded and is now being submitted as an indiviudals form

    const tinit  = findChildByName(div, name_tinit);
    const rinit  = findChildByName(div, name_rinit);
    const pinit  = findChildByName(div, name_pinit);

    const ttotal = findChildByName(div, name_ttotal);
    const rtotal = findChildByName(div, name_rtotal);
    const ptotal = findChildByName(div, name_ptotal);

    const tids = div.querySelectorAll(qs_tids);
    const rids = div.querySelectorAll(qs_rids);
    const pids = div.querySelectorAll(qs_pids);

    const tdels = div.querySelectorAll(qs_tdels);
    const rdels = div.querySelectorAll(qs_rdels);
    const pdels = div.querySelectorAll(qs_pdels);

    const ranks = div.querySelectorAll(qs_ranks);
    const rscores = div.querySelectorAll(qs_rscores);
    const pscores = div.querySelectorAll(qs_pscores);

    const pplayers = div.querySelectorAll(qs_pplayers);
    const rplayers = div.querySelectorAll(qs_rplayers);

	const team_switch = $$(id_team_switch);
	const team_play = team_switch.checked;
	console.log(`Was loaded as team play session: ${Session.team_play}`);
	console.log(`Is submitted as team play session: ${team_play}`);

	console.log(tinit.outerHTML);
	console.log(ttotal.outerHTML);
	console.log(`${tids.length} Team IDs:`);
    for (let tid of tids) console.log(tid.outerHTML);
	console.log(`${tdels.length} Deleted Team IDs:`);
    for (let tdel of tdels) console.log(tdel.outerHTML);

	console.log(rinit.outerHTML);
	console.log(rtotal.outerHTML);
	console.log(`${rids.length} Rank IDs:`);
    for (let rid of rids) console.log(rid.outerHTML);
	console.log(`${rdels.length} Deleted Rank IDs:`);
    for (let rdel of rdels) console.log(rdel.outerHTML);

	console.log(pinit.outerHTML);
	console.log(ptotal.outerHTML);
	console.log(`${pids.length} Performance IDs:`);
    for (let pid of pids) console.log(pid.outerHTML);
	console.log(`${pdels.length} Deleted Performance IDs:`);
	for (let pdel of pdels) console.log(pdel.outerHTML);

	console.log(`${ranks.length} Ranks:`);
    for (let rank of ranks) console.log(rank.outerHTML);

	console.log(`${rscores.length} Rank scores:`);
    for (let rscore of rscores) console.log(rscore.outerHTML);

	console.log(`${pscores.length} Performance scores:`);
    for (let pscore of pscores) console.log(pscore.outerHTML);

	// Performance player elements log as Select elements and show the selected item
	// Oddly while they show it the outerHTML reports selected=""
	console.log(`${pplayers.length} Performance players (the main driver):`);
    for (let pplayer of pplayers) console.log(pplayer.outerHTML);

	// Rank player elements log as hidden Input elements and show the value correctly
	console.log(`${rplayers.length} Rank players (a second copy in individual play mode):`);
    for (let rplayer of rplayers) console.log(rplayer.outerHTML);

    // We want to see if they map form numbers to players the same way -- that the rank player
    // if it exists (only relevant in individual player mode) is a copy of the Performance
    // player selection (this is just our way of ensureing bthat form number management survived
    // any mode transitions or such)
    for (let pplayer of pplayers) console.log(`${pplayer.name} => ${pplayer.selectedOptions[0].value}`); // Only one can be selected
    for (let rplayer of rplayers) console.log(`${rplayer.name} => ${rplayer.value}`);

	// If debugging only we are not submitting, and any sleectively disable tids, rids, or
	// pids should be re-enabled here so the form is not adversely affected by the pre-submission
	// removal of elements from the submission.
	for (let tid of tids) tid.disabled=false;
	for (let rid of rids) rid.disabled=false;
	for (let pid of pids) pid.disabled=false;
	for (let rank of ranks) rank.disabled=false;
	for (let rscore of rscores) rscore.disabled=false;
	for (let pscore of pscores) pscore.disabled=false;
}

function OnSubmit(event) {
	const print_debug_info = event.target.id === "prepare_submission";

	// Session.team_play reflects the state of the form when loaded.
	// In the context of this submission we rename it so that the
	// code reads more lucidly.
	const was_team_play = Session.team_play;

	// Remove the templates from the submission
	if ($$("templatePlayersTable")) $$("templatePlayersTable").remove();
	if ($$("templateTeamsTable")) $$("templateTeamsTable").remove();
	if ($$("templateTeamPlayersTable")) $$("templateTeamPlayersTable").remove();

	// Remove and elements flagged as NoSubmit by class
	const killthem = document.getElementsByClassName("NoSubmit");
	for (let i = 0; i < killthem.length; i++) killthem[i].disabled = true;

	// Tidy up the submission to meet Django formset expectations (to simplify processing when submitted)
	const team_switch = $$(id_team_switch);
	const team_play = team_switch.checked;

	// enable the team_switch if it was disabled
	// disabled elements don't get submitted with the POST
	// checkbox elements don't support the readonly attribute
	// only recourse is to disable it when not supported but
	// enable it here before submission so Django gets to see
	// it in the form submission (and save the session object
	// with this flag).
	team_switch.disabled = false;

	if (team_play) {
		const num_teams = $$(id_num_teams).value
    	const tbl_teams = $$(id_tbl_teams);
		const div = document.getElementById(id_teams_div);

		// Keep a count ranks, performancs and teams we've requested deletion of
		// (so we can number the forms properly, sort of like num_teams+deleted_ranks)
		let	deleted_ranks = 0;
		let	deleted_perfs = 0;
		let	deleted_teams = 0;

		// A performance pointer that helps us keep a list of perfs to upate followed by perfs to create
		let P = 0;

		// Keep a list of spare rank IDs
		let spare_rids = [];

		/*
		  Process  players (performances) in two passes, capturing all those with IDs first and
		  then those without.

		  Django expects INITIAL_FORMS and TOTAL_FORMS and the first INITIAL_FORMS items need IDs and the
		  rest need blank IDs and Django will create IDs for them after submission.

		  So pass 0 collect Ranks and Performances with IDs and Ranks
		     pass 1 collect Ranks and Performances without IDs

		  So we can build forms numbered 0 to INITIAL_FORMS-1 with IDs and then INITIAL_FORMS to TOTAL_FORMS-1 with blank IDs

		  Performances are hidden under the Ranked teams though, so we walk the teams and look inside them
		  at each player to extract the performances.

		  We manage Ranks in the same loop on the first pass only, walking through the teams and splitting out
		  any amalgamated IDs (which happen when a session is converted from individual play mode to team play mode
		  and players with individual ranks are merged into one team.
		*/
		for (let pass = 0; pass < 2; pass++)
			for (let t = 0; t < num_teams; t++) {
	            const box_num_players = findChildByName(tbl_teams, name_num_team_players.replace(form_number,t));
	            const num_players = box_num_players.value;

	            // Rank ID management happens in two passes as well but only for edits, for add
	            // oprations one pass suffices.
				const rid = getWidget(tbl_teams, name_rid, t);

				if (operation === "add" && pass == 0)
					rid.disabled=true; // Do not submit Rank IDs on add operations
				else if (operation === "edit") {
					// If rids were joined by any indiv->team conversion then joined_rids.length > 1
					const joined_rids = rid.value.split("&");

					// On the first pass we look for spare rank ids that appear in folded lists
		            // (i.e. all but the first). We remove them from the rank id, so the team has a unique
		            // rank id and keep them in a list. Any placeholder ids after the first one can be
		            // discarded in the same pass.
		            if (pass == 0) {
						// If we're editing, we had Rank IDs and now we may have some folded Ranks IDs
						// after a conversion from individual play to team play. These we have to unfold,
						// which means we keep the first one and request the remaining rank objects be deleted.
						if (joined_rids.length > 1) {
							// keep only the first one
							rid.value = joined_rids[0];

							// Catch the rest in our spare_rids list
							for (let r=1; r<joined_rids.length; r++) {
								const rID = joined_rids[r];

								// catch as a spare only if it's a real id not a placeholder
 								// placeholders after the first one (joined_rids[0]) can be safely
								// discarded in fact should be. That is, simply ignored here.
								if (!isNaN(rID)) spare_rids.push(rID);
							}
						}
		            }
		            // On the second pass we look for any placeholder ids, and use a spare rank id if it's
		            // available, to recycle it for use on this team. All the rids at this stage are not
		            // joined (were cleaned up in pass 0), and if more than 1 is left we have an integrity
		            // error in this code.
		            else if (pass == 1) {
						if (joined_rids.length == 1)
							if (isNaN(joined_rids[0])) {
								if (spare_rids.length > 0)
									rid.value = spare_rids.shift();
								else
									// If no spare rids are available do not submit the rid element at all
									// TODO: do we need to check that the management form is good
									// here, and/or ensure that all removed rids have a form number
									// above valid rids? Or does this code already ensure that? Perhaps,
									// because of the way we fold and unfold here? Needs a think.
									rid.disabled=true;
							}
						else if (joined_rids.length > 1)
							console.log("Code integrity error: a rank Id element was left with more than one rank ID after first pass of submission processing.");
		            }
				}

	            // Now on both passes we look at all players, but on pass 0 we build up P = 0, 1, 2, 3 ... n-1
	            // Until we've used all the PIDs, then on pass 1 we'll continue with P = n, n+1, n+2 ... m-1
	            // Which is why we neeed two passes
	    		for (let p = 0; p < num_players; p++) {
	    			// pid is found on first pass, but then if it has a value is renamed
	    			// so that on the second pass only those without value are left. The
	    			// original names have a form number in the format team.player (e.g. 1.2)
	    			// as this is how they've been managed in the form. We rename to 0, 1, 2, etc.
	    			// so on the second pass those without a value remai and still have the
	    			// compound form number so are easy to find.
	    			const cfn = t + "." + p;							// Compound Form Number
	    			const pid = getWidget(tbl_teams, name_pid, cfn);

	    			// On first pass do those which have a pid are grouped as form numbers 0, 1, 2, ... n
	    			// On the second pass those that are left get form numbers n+1, n+2, n+3 ...
	    			//
	    			// On the first pass we rename the pid widget from a t.p form_number to P
	    			// On the second pass those pids renamed on first pass are no longer found and pid is undefined
	    			// It is only pids that have no value that remain defined on the second pass.
	    			if ((pass == 0 && pid.value) || (pass == 1 && pid)) {
		    			// Fix the widget names from our internal t.p format to Django's expected integer index
		    			const pid 	  = fixWidget(tbl_teams, name_pid,    cfn, P);
		    			const player  = fixWidget(tbl_teams, name_player, cfn, P);
		    			const pscore  = fixWidget(tbl_teams, name_pscore, cfn, P);
		    			const weight  = fixWidget(tbl_teams, name_weight, cfn, P);
		    			P++;

		                // Add a hidden element that submits the team index number for this Performance.
		                // It is set so that the server can later (when submitted) associate the player
		    			// with other players on the same team. That is how we define teams, as a collection
		    			// of players.
		                const team_num  = document.createElement("input");
		                team_num.type 	= "hidden";
		                team_num.value 	= t;
		                team_num.id 	= pid.id.replace("-id", "-team_num")
		                team_num.name 	= pid.name.replace("-id", "-team_num")
		                pid.parentNode.appendChild(team_num);

		                // On Add operations do not submit the pid from the submission as a safety.
		                // Also on edits, if we have any pid control that lacks a valid id after
		                // edits we disable it to prevent submission. This can happen because players a
		                // re added to a game session in such an edit for example.
		                //
		                // Django will create ids for us when saving to the database.
		                if (pid && operation === "add" || !pid.value || isNaN(pid.value)) pid.disabled=true;
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
			            // prefix and suffix, expect one result and use that to get the value
			            const pid = row.querySelector(qs_pids);

						// Add a hidden pair of elements that convey the rank ID and the -DELETE request.
						// We need to use form numbers above those used by actual forms, so starting with
						// num_teams. That is forms 0, 1, 2 ... num_teams-1 will all have a rank for a team.
						// And forms num_teams,num_teams+1, num_teams+2 ... Are ones we can add delete
						// requests for. But we need to keep track of how many we've deleted.

						// Fix the pid element's name and id so that the form number is not in the t.p format
			            // but a plain P format.
		                pid.id 	 = id_pid.replace(form_number, P);
		                pid.name = name_pid.replace(form_number, P);

		                // Then add a -DELETE request in the form of a checkbox as Django expects.
		                const perf_del   = document.createElement("input");
		                perf_del.type 	 = "checkbox";
		                perf_del.value 	 = "on";
		                perf_del.checked = true;
		                perf_del.id 	 = pid.id.replace("-id", "-DELETE");
		                perf_del.name	 = pid.name.replace("-id", "-DELETE");
			            perf_del.style.display = 'none';
		                insertAfter(perf_del, pid);

		                P++; deleted_perfs++;
					}
	    		}
	        }

		// Check for any required DELETE requests
		if (operation == "edit") {
			// If after the rank management above there are still spare_rids we have to request their
			// deletion. they are rank IDs we don't need in the database). One use case is a 10 player
			// game session (individual mode) is loaded from database converted from indiv mode to
			// team and there are less thant 10 teams then some of the rids of those players will
			// remain spare.
			for (let r = 0; r < spare_rids.length; r++) {
				// Add a hidden pair of elements that convey the rank ID and the -DELETE request.
				// We need to use form numbers above those used by actual forms, so starting with
				// num_teams. That is forms 0, 1, 2 ... num_teams-1 will all have a rank for a team.
				// And forms num_teams, num_teams+1, num_teams+2 ... Are ones we can add delete
				// requests for. But we need to keep track of how many we've deleted.
				const fn = Number(num_teams) + Number(deleted_ranks);

				// We need to add an ID field to identify the Rank
		        const rank_id = document.createElement("input");
		        rank_id.type 	= "hidden";
		        rank_id.value 	= spare_rids[r];
		        rank_id.id 		= id_rid.replace(form_number, fn)
		        rank_id.name	= name_rid.replace(form_number, fn)
		        tbl_teams.parentNode.appendChild(rank_id);

				// And a -DELETE checkbox to request its deletion
		        const rank_del = document.createElement("input");
		        rank_del.type 	 = "checkbox";
		        rank_del.value 	 = "on";
		        rank_del.checked = true;
		        rank_del.id 	 = rank_id.id.replace("-id", "-DELETE");
		        rank_del.name 	 = rank_id.name.replace("-id", "-DELETE");
		        rank_del.style.display = 'none';
		        tbl_teams.parentNode.appendChild(rank_del);

		        deleted_ranks++;
			}

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
	            // prefix and suffix, expect one result and use that to submit a DELETE
	            // request (as it's in the trash)
	            const rid = row.querySelector("[id^=['"+id_prefix+rank_prefix+"'][id$='-id']");

	            if (rid.value && !isNaN(rid.value)) {
					// Fix the rid element's name and id so that the form number is properly in sequence
		            let fn = Numer(num_teams) + Number(deleted_ranks);
	                rid.id 	 = id_pid.replace(form_number, fn);
	                rid.name = name_pid.replace(form_number, fn);

	                // Then add a -DELETE request in the form of a checkbox as Django expects.
		            const rank_del = document.createElement("input");
		            rank_del.type 	 = "checkbox";
		            rank_del.value 	 = "on";
		            rank_del.checked = true;
		            rank_del.id 	 = rid.id.replace("-id", "-DELETE");
		            rank_del.name	 = rid.name.replace("-id", "-DELETE");
		            rank_del.style.display = 'none';
	                insertAfter(rank_del, rid);

	                deleted_ranks++;
	            } else {
					// If the trash element has no valid rid, then simply don't submit it
	            	rid.disabled=true;
	            }

	            // Same deal for team IDs
	            const tid = row.querySelector("[id^=['"+team_prefix+"'][id$='-id']");

	            // tid values may just be a placeholder of id_n if this was loaded as an individual
	            // play mode session and then switched to team mode, then teams are created and given
	            // these mock IDs so that we can manage the form. But Django doesn't know about them
	            // and so doesn't need to and can't delete them.
	            if (tid.value && !/^id_\d+$/.test(team_id.value)) {
					// Fix the tid element's name and id so that the form number is properly in sequence
		            let fn = Number(num_teams) + (deleted_teams);
	                tid.id 	 = id_pid.replace(form_number, fn);
	                tid.name = name_pid.replace(form_number, fn);

	                // Then add a -DELETE request in the form of a checkbox as Django expects.
		            const team_del = document.createElement("input");
		            team_del.type 	 = "checkbox";
		            team_del.value 	 = "on";
		            team_del.checked = true;				   teams
		            team_del.id 	 = tid.id.replace("-id", "-DELETE");
		            team_del.name 	 = tid.name.replace("-id", "-DELETE");
	                insertAfter(team_del, tid);

	                deleted_teams++;
	            } else {
					// If the trash element has no valid tid, then simply don't submit it
	            	tid.disabled=true;
	            }
			}
		}

		// If submitting teams tidy up the submission a tad. We may have
		// some mock IDs and names (placeholders) in place auto filled from either
		// a conversion from individual play (in the case of Team IDs) or simply a
		// form creation (in the the case of Team Name). Neither should be submitted
		// in that form
		for (let t=0; t<num_teams; t++) {
			const team_id = getWidget(tbl_teams, name_tid, t);
			const team_name = getWidget(tbl_teams, name_team_name, t);

			// Do not submit invalid IDs
			if (team_id != undefined && isNaN(team_id.value)) team_id.disabled=true;

			// Submit an empty name if it's just a placeholder value (This makes it
			// impossible to name ream teams in the format "Team n" of course.
			team_name.value = /^Team \d+$/.test(team_name.value) ? "" : team_name.value;

			// If we have no team name, don't submit it
			if (team_name.value === "") team_name.disabled=true;
		}

		// Don't submit hidden ranks/scores'
		disable_ranks_scores_as_needed(div);

		// We have to add the number of deleted forms to the TOTAL_FORMS field in the management form
		// or Django will ignore them (i.e. only process TOTAL_FORMS forms not these extra ones.
		updateManagementForms(div);

		if (print_debug_info)
			submission_debug(div);
		else
			// Remove the individual play form completely before submitting
			if ($$(id_indiv_div)) $$(id_indiv_div).remove();
	}

	// it's individual play (the team_play checkbox is not checked)
	else {
		const num_players = Number($$(id_num_players).value);
		const div = document.getElementById(id_indiv_div);

        // On Add operations remove the rid and pid for each player from the submission as a safety.
		// Django will create ids for us when saving to the database. So we don't submit rids and pids
		if (operation === "add") {
	    	const table = $$(id_tbl_players);

			for (let p = 0; p < num_players; p++) {
				const rid = getWidget(table, name_rid, p);
				const pid = getWidget(table, name_pid, p);

                if (rid) rid.disabled=true;
                if (pid) pid.disabled=true;
			}
		} else {
			/*
			  It's an individual play mode session being submitted but it may have been
			  a team play session when loaded (if this is an edit form).

			  In that case there may be teams that are no longer relevant and need deletion
			  and ranks certainly need updating from team to player references. The latter
			  must be done server side, on client side here we can check for any deleted
			  teams and ensure we add -DELETE requests to the submission.

			  The server should only delete such teams of course if there are no references
			  left to that team and so these -DELETE requests still need server side attention.
			*/
			if (was_team_play) {
				/*
				   Teams that existed when the form was loaded are no longer needed and can
				   be marked for deletion in the server submission. They could be in either
				   the teams table or the teams trash depending on the edits that happened
				   before it was made an individual play session. All teams, be they in the
				   teams table or the teams trash table are marked for deletion.

				   It is the server side reponsibility to NOT delete teams that have other
				   session references to them, just to remove this sessions reference to them.
				   Not ours.
				   TODO: Ensure this is tested.
				*/
				const id_template = "templateTeamsTable";
				const id_table = id_template.replace("template", "tbl");
				const id_trash = id_table.replace("tbl", "trash");
				const table = $$(id_table);
				const trash = $$(id_trash);

		    	const div_players = $$(id_indiv_div);

				let T = 0;
				for (let tbl of [table, trash]) {
					for (let row of tbl.rows) {
						// There's a hidden element holding the Team ID with an id in the format:
						// 		id_Team-n-id
						// which is generalsied to the pattern:
						//		id_prefix+team_prefix+ n +"-id"
						// We have one row of a teams or trash table here and it has one tid element
						// in it with one form_number n. We don't care what that form number is, only
						// want to find the element and extract the team ID from it if there.
			            const tid = row.querySelector(qs_tids);

			            // If the TID element has no value then we have no team to delete, but if it does ...
			            // the TID element has no value on add forms and on teams that were added on an edit form
			            // by increasing the number of teams. Also tid will be undefined on the table header row.
			            if (tid && tid.value) {
				            // Add a hidden pair of elements (that convey the team ID and the -DELETE request)
				            // to the submitted division (individual play mode session). These will identify
				            // the team and request its deletion and must be in the submitted division
				            // (only one of $$(id_indiv_div) or $$(id_team_div) will be submitted.
			                const team_id = document.createElement("input");
			                team_id.type  = "hidden";
			                team_id.value = tid.value;
			                team_id.id 	  = id_tid.replace(form_number, T)
			                team_id.name  = name_tid.replace(form_number, T)
			                div_players.appendChild(team_id);

			                const team_del   = document.createElement("input");
			                team_del.type 	 = "checkbox";
			                team_del.value 	 = "on";
			                team_del.checked = true;
			                team_del.id 	 = team_id.id.replace("-id", "-DELETE");
			                team_del.name	 = team_id.name.replace("-id", "-DELETE");
				            team_del.style.display = 'none';
			                div_players.appendChild(team_del);

			                T++;
			            }
					}
				}

				/*
				  Having dealt with team IDs we need to deal with Rank IDs. The thing is if a team session
				  is converted to individual play, then there's only one rank per team and only one of the players
				  from the erstwhile team can get that rank the others will have placeholders (in form id_n.m)
				  At a bare minimum we need these placeholders removed so that Django creates new Rank objects
				  with new IDs when saving. But we also want to order the forms in such a way that the ones
				  with Rank IDs are 0 to n and the ones without are n+1 to m.

				  First let's fetch all the rid elements
				*/
	            const rids = $$(id_indiv_div).querySelectorAll(qs_rids);

				// Get the form numbers (fns) and classify them
	            let rid_fns_now = [];
	            let rid_fns_good = [];
	            let rid_fns_bad = [];
				for (let r=0; r<rids.length; r++) {
					const fn = Number(getFormNumber(rids[r].id));
					rid_fns_now.push(fn);

					if (isNaN(rids[r].value)) {
						rid_fns_bad.push(fn);
						rids[r].disabled=true; // Don't submit bad rids
					} else
						rid_fns_good.push(fn);
				}

				// And build a new list of form numbers
	            let rid_fns_new = [];
				for (let f=0; f<rid_fns_good.length; f++) rid_fns_new.push(rid_fns_good[f]);
				for (let f=0; f<rid_fns_bad.length; f++) rid_fns_new.push(rid_fns_bad[f]);

				// Now if the two lists differ we have to map the form numbers to the new form numbers
				// but that involves renumbering all the form elements from one index to the next
				// The beauty is that POSTed data is keyed on element names, not IDs and by default
				// the names and IDs all hold the same form number, so we need only change the name, not
				// the ID of the form elements in order to produce a clean POST.
				for (let f=0; f<rid_fns_now.length; f++)
	            	mapElementNames($$(id_indiv_div), ["Rank", "Performance"], rid_fns_now[f], rid_fns_new[f]);
			}
			else {
				// We are editing a session that had session.team_play=false when the form was initialised.
				// We have to check the trash for deleted players. We have a rank ID and a performance ID
				// for each one that we need to request the deletion of.
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
		            const rid = row.querySelector(qs_rids);
		            const pid = row.querySelector(qs_pids);

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

		// Don't submit hidden ranks/scores'
		disable_ranks_scores_as_needed(div);

		// We have to add the number of deleted forms to the TOTAL_FORMS field in the management form
		// or Django will ignore them (i.e. only process TOTAL_FORMS forms not these extra ones.
		updateManagementForms(div);

		if (print_debug_info)
			submission_debug(div);
		else
			// Remove the team play form completely before submitting
			if ($$(id_teams_div)) $$(id_teams_div).remove();

	}
}

// Re-configures the form for a new game if the game is changed (on an edit form).
function configureGame() {
	// If these aren't available (because the game doesn't support team play) set some sensible defaults presuming individual mode.
	if (game_min_players_per_team == 0) game_min_players_per_team = 1;
	if (game_max_players_per_team == 0) game_max_players_per_team = 1;

    // Set some useful derived globals
	game_min_teams = Math.max(game_min_players/game_max_players_per_team, 2);
	game_max_teams = Math.max(game_max_players/game_min_players_per_team, 2);

	// Reads the global game options and ses the play mode as needed and limits the player counts as needed.
	const team_switch = $$(id_team_switch);

	// game_individual_play is true if the game supports individual play mode
	// game_team_play is true if the game supports team play mode
	// These are game properties.

	// Decide which mode (individual play or team play to display)
	let show_team_play = false;

	// If the game supports both modes, the Team play selector will have been delivered
	// by Django with a default value and we respect that
	if (game_team_play && game_individual_play) show_team_play = team_switch.checked;

	// If the game supports only one mode, force that mode.
	else if (game_individual_play && !game_team_play) show_team_play = false;
	else if (game_team_play && !game_individual_play) show_team_play = true;

	if (show_team_play) {
		if (!team_switch.checked) {
			team_switch.checked = true;
			switchMode();
		}

		const num_teams = $$(id_num_teams);
		if (num_teams.value < game_min_teams) num_teams.value = game_min_teams;
		if (num_teams.value > game_max_teams) num_teams.value = game_max_teams;
		num_teams.defaultValue = num_teams.value;
		num_teams.tabIndex = 1;
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

		showDiv("teams");
	} else {
		if (team_switch.checked) {
			team_switch.checked = false;
			switchMode();
		}

		const num_players = $$(id_num_players);
		if (num_players.value < game_min_players) num_players.value = game_min_players;
		if (num_players.value > game_max_players) num_players.value = game_max_players;
		num_players.defaultValue = num_players.value;
		num_players.tabIndex = 1;
		num_players.setAttribute('min', game_min_players);
		num_players.setAttribute('max', game_max_players);

		adjustTable(num_players);

		showDiv("indiv");
	}

	// Else do nothing, the form can stay in the mode its in (Individual or Team Play)

	// But in all cases lock the team switch if only one mode is available.
	const lock = (!game_individual_play || !game_team_play);
	team_switch.disabled = lock;
}

// Event handler for a new game selection
function switchGame(event) {
	const selector = event.target;
	const game_pk = selector.value;
	const url = game_props_url.replace(/\d+$/, game_pk); // Replace the dummy Game PK with the selected one

	let REQUEST = new XMLHttpRequest();

	REQUEST.onreadystatechange = function () {
	    if (this.readyState === 4 && this.status === 200){
	        // the request is complete, parse data
	        const response = JSON.parse(this.responseText);

	        // and save in the global game properties
	        game_individual_play 	  = response.individual_play;
			game_team_play 			  = response.team_play;
			game_scoring 			  = response.scoring;
			game_min_players 		  = response.min_players;
			game_max_players 		  = response.max_players;
			game_min_players_per_team = response.min_players_per_team;
			game_max_players_per_team = response.max_players_per_team;

			if (game_team_play) {
				show_rank_scores = game_scoring.includes("TEAM");
				show_perf_scores = game_scoring.includes("INDIVIDUAL");
			} else {
				show_rank_scores = game_scoring.includes("INDIVIDUAL");
				show_perf_scores = false;
			}

			showhideRankScoreColumns();
			configureGame();
	    }
	};

	REQUEST.open("GET", url, true);
	REQUEST.send(null);
}

// Event handler for new play mode selection (swapping from Individual to Team or vice versa)
function switchMode(event) {
	const team_switch = $$(id_team_switch);

	const table_players = $$(id_tbl_players);
	const table_teams = $$(id_tbl_teams);

    if (team_switch.checked && table_players != undefined) {
    	// Switch from individual play to team play
		const num_teams = $$(id_num_teams);

		const session = get_converted_session_data_from(table_players);

		num_teams.value = session["rIDs"].length;
		num_teams.defaultValue = num_teams.value;

		// before adjusting tables set the globals
		// communicating score widget display preferences.
		show_rank_scores = game_scoring.includes("TEAM");
		show_perf_scores = game_scoring.includes("INDIVIDUAL");

		const table_teams = adjustTable(num_teams, session);

		for (let t=0; t<num_teams.value; t++) {
	    	const real_name_num_team_players = name_num_team_players.replace(form_number,t);
	    	const id_table = 'tblTeamsBody' + t;
	    	const table_teams = $$(id_table);
			const num_team_players = findChildByName(table_teams, real_name_num_team_players);

			adjustTable(num_team_players, session);
		}

		showhideRankScoreColumns(id_teams_div);
		showDiv("teams");
    } else if (!team_switch.checked && table_teams != undefined) {
    	// Switch from team play to individual play
		const num_players = $$(id_num_players);

		const session = get_converted_session_data_from(table_teams);

		num_players.value = session["rIDs"].length;
		num_players.defaultValue = num_players.value;

		// before adjusting tables set the globals
		// communicating score widget display preferences.
		show_rank_scores = game_scoring.includes("INDIVIDUAL");
		show_perf_scores = false;

		adjustTable(num_players, session);

		showhideRankScoreColumns(id_indiv_div);
		showDiv("indiv");
    }

	// If there are any rank ties we should show the Break ties checkbox
	manage_rank_ties();
}

// The table shave columns for ranks and scores. Depending on the game.scoring configuration
// either ranks or scores are relevant for data entry. Two globals are maintained on page load
// and impacting context switches, namly if the game is changed, or if the team_play mode is
// changed. They are "show_rank_scores" and "show_perf_scores" respectively, from which we can
// infer what to do. The respective cells (th and td elements) all have class rank_column and
// rscore_column and pscore_column to make them easy to find.
//
// A third global "show_tiebreakers" requests that ranks are shown when the would not otherwise
// be, so that they can be entered to break ties.
//
// Note: applySessionToRow applies visibility to these columns when the table rows are created.
//       at load time or when team/player counts change too. But this should be called before
// 		 rows are built to catch the table headers.
function showhideRankScoreColumns(element_id) {
	const team_switch  = document.getElementById(id_team_switch);
	const team_play    = team_switch.checked;

	if (element_id == undefined) element_id = team_play ? id_teams_div : id_indiv_div;
	const element = document.getElementById(element_id);

	const rank_cells   = element.querySelectorAll('.rank_column');   // Can be inferred from scores if needed
	const rscore_cells = element.querySelectorAll('.rscore_column'); // Can be used in place of ranks
	const pscore_cells = element.querySelectorAll('.pscore_column'); // Only needed for TEAM_AND_INDIVIDUAL scoring games

	if (debug_ranks_and_scores) {
		rank_cells.forEach(cell => cell.style.display = "table-cell");
		rscore_cells.forEach(cell => cell.style.display = "table-cell");
		if (team_play) pscore_cells.forEach(cell => cell.style.display = "table-cell");
	} else {
		rank_cells.forEach(cell => cell.style.display = (show_rank_scores && !show_tiebreakers) ? "none" : "table-cell");
		rscore_cells.forEach(cell => cell.style.display = show_rank_scores ? "table-cell" : "none");
		if (team_play) pscore_cells.forEach(cell => cell.style.display = show_perf_scores ? "table-cell" : "none");
	}
}

// Collect session data from the visible table/div
// Centralises the logic of the field mapping from form controls to the session dict
function collect_session_data() {
	const from_table = $$(id_tbl_visbl);

	if (id_tbl_visbl == id_tbl_players) {
		// Individual player mode
		//
		// We look for
		//	one rank_id per player in widget name_rid
		// 	one rank per player in the widget with name_rank
		// 	one rank score per player in the widget with name_rscore
		//	one performance id per player in widget name_pid
		//  one player id per player in widget name name_player
		//	one partial play weight per player in widget name_weight
		//
		// All names have an embedded form_number which is 0, 1, 2, 3 sequentially for each player on the form.
		//
		// The number of players is stored in id_num_players
		const rIDs = [];		// Array of rank IDs
		const ridRanks = {};	// dict of ranks keyed on rID
		const ridScores = {};	// dict of scores keyed on rID
		const ridPlayers = {}; 	// dict of player IDs keyed on rID
		const pIDs = [];		// Array of performance IDs
		const pidPlayers = {};	// dict of player IDs keyed on pID
		const pidWeights = {};	// dict of performance weights keyed on pID

		const team_play = false;
		const num_players = Number($$(id_num_players).value);

		// Walk all players adding to the lists declared above.
		for (let p=0; p<num_players; p++) {
			// Get the widgets from the Players table. Each player has a rank (rid)
			const rid 		= getWidget(from_table, name_rid, p);
			const rank 		= getWidget(from_table, name_rank, p);
			const rscore 	= getWidget(from_table, name_rscore, p);
			const pid 		= getWidget(from_table, name_pid, p);
			const plid 	    = getWidget(from_table, name_player, p);
			const weight 	= getWidget(from_table, name_weight, p);

			// Get values for all the fields, but store placeholder values of the form id_n
			// where none is available because the Session object we're building wants to use
			// id's for indexes and so for forms that have no ids (like when creating a new
			// session), a unique placeholder in the dict keys is fine.
			const default_id = id_prefix+p;

			// Rank ID keyed items first
			const rID = getNumberValue(rid, default_id);
			const rVal = getNumberValue(rank, null);
			const rsVal = getNumberValue(rscore, null);

			// Performance ID keyed items next
			const pID = getNumberValue(pid, default_id);
			const plID = getNumberValue(plid, default_id);
			const wVal = getNumberValue(weight, 1);

			// Now build the arrays and dicts
			rIDs.push(rID);
			ridRanks[rID] = rVal;
			ridScores[rID] = rsVal;
			ridPlayers[rID] = plID;

			pIDs.push(pID);
			pidPlayers[pID] = plID;
			pidWeights[pID] = wVal;
		}

		return session_dict(
					 team_play,
					 // Rank ID (rID) keyed dicts
					 rIDs, 			// Array of rank IDs
					 ridRanks,		// dict of ranks keyed on rID
					 ridScores,	    // dict of scores keyed on rID
					 ridPlayers,	// dict of player IDs keyed on rID
					 {}, 			// dict of team IDs keyed on rID
					 // Team ID (tID) keyed dicts
					 {}, 			// dict of team names keyed on tID.
					 {}, 			// dict of team player lists keyed on tID with list of player IDs as value
					 // Performance ID (pID) keyed dicts
					 pIDs,			// Array of performance IDs
					 pidPlayers, 	// dict of player IDs keyed on pID
					 {}, 			// dict of performance scores keyed on pID
					 pidWeights		// dict of performance weights keyed on pID
				);
	} else {
		// Team player mode
		//
		// We look for
		//	one rank_id per team in widget name_rid
		// 	one rank per team in the widget with name_rank
		// 	one rank score per team in the widget with name_rscore
		//	one team name per team in the widget name_team_name
		//	one performance id per player in widget name_pid
		//  one player id per player in widget name name_player
		// 	one player score per player in the widget with name_pscore
		//	one partial play weight per player in widget name_weight
		//
		// All names have an embedded form_number which is 0, 1, 2, 3 sequentially for each player on the form.
		//
		// The number of players is stored in id_num_players
		const rIDs = [];			// Array of rank IDs
		const ridRanks = {};		// dict of ranks keyed on rID
		const ridScores = {};		// dict of scores keyed on rID
		const ridTeams = {};		// dict of team IDs keyed on rID
		const tidTeamNames = {}; 	// dict of team names keyed on tID.
		const tidTeamPlayers = {};	// dict of team player lists keyed on tID with list of player IDs as value
		const pIDs = [];			// Array of performance IDs
		const pidPlayers = {};		// dict of player IDs keyed on pID
		const pidScores = {};		// dict of scores keyed on pID
		const pidWeights = {};		// dict of performance weights keyed on pID

		const team_play = true;
		const num_teams = Number($$(id_num_teams).value);

		for (let t=0; t<num_teams; t++) {
			// Rank ID keyed items (Performance ID items come from the embracing teams table)
			const rid 		= getWidget(from_table, name_rid, t);
			const rank 		= getWidget(from_table, name_rank, t);
			const rscore 	= getWidget(from_table, name_rscore, t);
			const team_name = getWidget(from_table, name_team_name, t);

			const rVal      = getNumberValue(rank, t);
			const rsVal     = getNumberValue(rscore, null);


			// rIDs and rID keyed dicts
			rIDs.push(rid.value);
			ridRanks[rid.value] = rVal;
			ridScores[rid.value] = rsVal;

			// We don't use actual team IDs int he front end, only proxy ones.
			// Teams are managed server side by the set of players in them that defines the team,
			const tID = id_prefix + t;

			// tIDs and tID keyed dicts
			ridTeams[rid.value] = tID;
			tidTeamNames[tID] = team_name.value;

			// Collect the player data from all the team members
			// And add to tidTeamPlayers after we have them.
			const team_players = [];

			// The number of players in the team at this rank
			const real_name_num_team_players = name_num_team_players.replace(form_number,t);
			const num_team_players = findChildByName(from_table, real_name_num_team_players).value;


			for (let p=0; p<num_team_players; p++) {
				const form_num  = t+"."+p;
				// Performance ID keyed items (Rank ID items come from the embracing teams table)
				const pid 		= getWidget(from_table, name_pid, form_num);
				const plid 	    = getWidget(from_table, name_player, form_num);
				const pscore 	= getWidget(from_table, name_pscore, form_num);
				const weight 	= getWidget(from_table, name_weight, form_num);

				// Get values for all the fields, but store placeholder values of the form id_n
				// where none is available because the Session object we're building wants to use
				// id's for indexes. We'll have to make sure before we submit that any such
				// placeholder values are removed. Because we are converting from a teams table
				// the unique id n is of a t.p format (so each performance and player has a unique
				// id placeholder)
				const default_id = id_prefix+form_num;
				const pID = getNumberValue(pid, default_id);
				const plID = getNumberValue(plid, default_id);
				const psVal = getNumberValue(pscore, null);
				const wVal = getNumberValue(weight, 1);

				// pIDs and pID keyed dicts
				pIDs.push(pID);
				pidPlayers[pID] = plID;
				pidScores[pID] = Number.isInteger(psVal) && psVal > 0 ? psVal : null;
				pidWeights[pID] = wVal;

				team_players.push(plID);
			}

			tidTeamPlayers[tID] = team_players;
		}

		return session_dict(
					 team_play,
					 // Rank ID (rID) keyed dicts
					 rIDs, 			// Array of rank IDs
					 ridRanks,		// dict of ranks keyed on rID
					 ridScores,		// dict of scores keyed on rID
					 {},			// dict of player IDs keyed on rID
					 ridTeams, 		// dict of team IDs keyed on rID
					 // Team ID (tID) keyed dicts
					 tidTeamNames, 	// dict of team names keyed on tID.
					 tidTeamPlayers,// dict of team player lists keyed on tID with list of player IDs as value
					 // Performance ID (pID) keyed dicts
					 pIDs,			// Array of performance IDs
					 pidPlayers, 	// dict of player IDs keyed on pID
					 pidScores, 	// dict of performance scores keyed on pID
					 pidWeights		// dict of performance weights keyed on pID
				);
	}
}

// from_table can be one of tblIndividualPlay or tblTeamPlay from the associated template
// Will extract from the widgets data to fill a session data dictionary specifically for
// transition of the presentation mode (indivual to team play or vice versa)
function get_converted_session_data_from(from_table) {
	// TODO: the to_table is also relevant for round tripping!
	//       Because we have a Players table and a Teams Table in two divs
	//       Those tables can hold information. That is we can conserve
	//       player scores indeed and ranks etc.
	// Consider: defining the to_table based on the provided from_table (the other one)
	//           and fetching data form it too and comparing as we build the session.
	//           This might make round tripping more robust even clean.

	if (from_table.id == id_tbl_players) {
		// Collecting a teams/teamplayers Session from a players table.
		//
		// We look for
		//	one rank_id per player in widget name_rid
		// 	one rank per player in the widget with name_rank
		// 	one rank score per player in the widget with name_rscore
		//	one performance id per player in widget name_pweightid
		//  one player id per player in widget name name_player
		//	one partial play weight per player in widget name_weight
		//
		// All names have an embedded form_number which is 0, 1, 2, 3 sequentially for each player on the form.
		//
		// The number of players is stored in id_num_players
		//
		// We will create one team per game_min_players_per_team,and fold rIDs together in the team rID
		// as an & separated list. The last team if needed will accept the remainder.
		const rIDs = [];			// Array of rank IDs
		const ridRanks = {};		// dict of ranks keyed on rID
		const ridScores = {};		// dict of scores keyed on rID
		const ridTeams = {};		// dict of team IDs keyed on rID
		const tidTeamNames = {};	// dict of team names keyed on tID.
		const tidTeamPlayers = {};	// dict of team player lists keyed on tID with list of player IDs as value
		const pIDs = [];			// Array of performance IDs
		const pidPlayers = {};		// dict of player IDs keyed on pID
		const pidScores = {};		// dict of performance scores keyed on pID
		const pidWeights = {};		// dict of performance weights keyed on pID

		// Get the number of teams and players respecting minima specifed by globals
		// game_min_teams and game_min_players_per_teamn trying to divide up the specifed
		// number players into teams and then padding out the number of players if needed
		// to satsify the mimima specified.
		// The teams session may thus have more players in it than were provided in the
		// players table!
		const team_play = true;
		const np = Number($$(id_num_players).value);
		const num_teams = Math.max(game_min_teams, Math.trunc(np / game_min_players_per_team));
		const num_players = Math.max(np, game_min_teams * game_min_players_per_team);

		// Walk all players adding to the lists declared above.
		// A couple of accumulators for move to Rank ID keyed items in a second loop
		const ranks = [];
		const rscores = [];
		for (let p=0; p<num_players; p++) {
			// The team this player lands in
			const t = Math.trunc(p / game_min_players_per_team);
			const tID = id_prefix+t;

			// Get the widgets from the Players table. Each player has a rank (rid)
			// But we're moving to teams where each team has a rid, so we will
			// use a code where the rid for a team is the & separtaed list of player
			// rids. We do this to facilitate moving back and forth between modes
			// losslely and so that if a change is made and submitted, server side
			// know to fix the ranks appropriately in the database.
			// Rank ID keyed items first
			const rid 		= getWidget(from_table, name_rid, p);
			const rank 		= getWidget(from_table, name_rank, p);
			const rscore 	= getWidget(from_table, name_rscore, p);
			// Performance ID keyed items next
			const pid 		= getWidget(from_table, name_pid, p);
			const plid 	    = getWidget(from_table, name_player, p);
			const pscore 	= getWidget(from_table, name_pscore, p);
			const weight 	= getWidget(from_table, name_weight, p);

			// Get values for all the fields, but store placeholder values of the form id_n
			// where none is available because the Session object we're building wants to use
			// id's for indexes. We'll have to make sure before we submit that any such
			// placeholder values are removed.
			const default_id = id_prefix+p;
			// Rank ID keyed items first
			const rID = getNumberValue(rid, default_id);
			const rVal = getNumberValue(rank, t+1);
			const rsVal = getNumberValue(rscore, null);

			// Performance ID keyed items next
			const pID = getNumberValue(pid, default_id);
			const plID = getNumberValue(plid, default_id);
			const psVal = getNumberValue(pscore, null);
			const wVal = getNumberValue(weight, 1);

			tidTeamNames[tID] = "Team " + t;

			// The first player in a team
			if (rIDs.length <= t) {
				// Then start the lists for each team
				rIDs.push(rID);
				tidTeamPlayers[tID] = [plID];

				// Accumulators for later move Rank ID keyed lsits ridRanks and ridScores
				ranks[t] = rVal;
				if (rsVal) rscores[t] = rsVal; // Accumulate (sum up) the rank scores of the players to team rank scores
				else rscores[t] = null;
			}
			// Subsequent players in the team
			else {
				// Add a player to the list (folding them together as a & separted string of IDs)
				rIDs[t] = rIDs[t] + "&" + rID;
				tidTeamPlayers[tID].push(plID);

				// Accumulators for later move Rank ID keyed lsits ridRanks and ridScores
				if (rsVal) rscores[t] += rsVal; // Accumulate the ranks scores of the players
			}

			pIDs.push(pID);
			pidPlayers[pID] = plID;
			pidWeights[pID] = wVal;

			// Indiv mode player scores are rank scores (rank linked) and performance scores aren't used.
			// In team mode rank scores are used and maybe performance scores. So converting from individual
			// to team we accumulated the scrores for a tream (rank) score, and conserve the players scores
			// pid scores. The source in each case is psVal if a value is available else rsVal.
			pidScores[pID] = psVal == null ? rsVal : psVal;
		}

		// We have read a players table (to move to a teams  session)
		// the rIDs now contain & delimted (string)lists of erstwhile player rank IDs
		// the ranks of each team were taken from the rank fo the first player in that team.
		//    This won't be reversible. Round tripping Indiv>Team>Indiv will lose Indiv ranks
		//    The move back (below) will give all player son the team the team rank (a tie)
		//    Accepted as a tolerable edge case.
		// the scores for each team were taken as the sum of all player scores
		//    This won't be reversible. Round tripping Indiv>Team>Indiv will lose Indiv scores
		//    The move back (below) will give all players on the team one nth of the team score
		//    to permit round tripping of a sort that works. But individual scores will be lost
		//    int the transition to team and back.
		//    Accepted as a tolerable edge case.
		for (let t=0; t< rIDs.length; t++) {
			const rID = rIDs[t];
			const tID = id_prefix+t;

			ridTeams[rID] = tID;
			ridRanks[rID] = ranks[t];
			ridScores[rID] = rscores[t];
		}

		return session_dict(
					 team_play,
					 // Rank ID (rID) keyed dicts
					 rIDs, 			// Array of rank IDs
					 ridRanks,		// dict of ranks keyed on rID
					 ridScores,		// dict of scores keyed on rID
					 {},			// dict of player IDs keyed on rID
					 ridTeams, 		// dict of team IDs keyed on rID
					 // Team ID (tID) keyed dicts
					 tidTeamNames, 	// dict of team names keyed on tID.
					 tidTeamPlayers,// dict of team player lists keyed on tID with list of player IDs as value
					 // Performance ID (pID) keyed dicts
					 pIDs,			// Array of performance IDs
					 pidPlayers, 	// dict of player IDs keyed on pID
					 pidScores, 	// dict of performance scores keyed on pID
					 pidWeights		// dict of performance weights keyed on pID
				);
	}
	else if (from_table.id == id_tbl_teams) {
		// Collecting an individual players Session from a team/teamplayers table.
		//
		// We look for
		//	one rank_id per team in widget name_rid
		// 	one rank per team in the widget with name_rank
		//	one team name per team in the widget name_team_name
		//	one performance id per player in widget name_pid
		//  one player id per player in widget name name_player
		// 	one player score per player in the widget with name_pscore
		//	one partial play weight per player in widget name_weight
		//
		// The team properties have an embedded form_number which is 0, 1, 2, 3 sequentially for each team on the form.
		// The player properties have an embedded form_number which is of form t.p where t and p are 0, 1, 2, 3 sequentially
		// t being the team form number and p being the player form number inside of the team.
		//
		// The number of teams is stored in id_num_teams and the number of players in each team in name_num_team_players
		// which has form_number in it of 0, 1, 2, 3 etc for each team.

		// Initialise the session data buckets
		// Rank ID keyed
		let rIDs = [];		// Array of rank IDs
		let ridRanks = {};	// dict of ranks keyed on rID
		let ridScores = {};	// dict of scores keyed on rID
		let ridPlayers = {};// dict of player IDs keyed on rID
		// As we are moving from a team table to an individual play table
		// we don't need the Team ID indexed elements
		// Performance ID keyed
		let pIDs = [];		// Array of performance IDs
		let pidPlayers = {};// dict of player IDs keyed on pID
		let pidWeights = {};// dict of performance weights keyed on pID

		const team_play = false; // We're generating an indivicual play session (from a team play form)'
		const num_teams = $$(id_num_teams).value;
		for (let t=0; t<num_teams; t++) {
			// Rank ID keyed items (Performance ID items come from the embracing teams table)
			const rid 		= getWidget(from_table, name_rid, t);
			const rank 		= getWidget(from_table, name_rank, t);
			const rscore 	= getWidget(from_table, name_rscore, t);
			const team_name = getWidget(from_table, name_team_name, t);

			const rVal      = getNumberValue(rank, t);
			const rsVal     = getNumberValue(rscore, null);

			// The number of players in the team at this rank
			const real_name_num_team_players = name_num_team_players.replace(form_number,t);
			const num_team_players = findChildByName(from_table, real_name_num_team_players).value;

			// Collect the player data from all the team members
			const rids    = rid.value.split("&");    // rIDs may have been folded from a previous individual->team mode conversion (above)
			const pids    = []; // Performance IDs
			const plids =   []; // Player IDs
			const ranks   = []; // Ranks for each player in the team
			const scores  = []; // Scores fo each player (pscore if possible else rscore)
			const weights = [];
			for (let p=0; p<num_team_players; p++) {
				const form_num  = t+"."+p;
				// Performance ID keyed items (Rank ID items come from the embracing teams table)
				const pid 		= getWidget(from_table, name_pid, form_num);
				const plid 	    = getWidget(from_table, name_player, form_num);
				const pscore 	= getWidget(from_table, name_pscore, form_num);
				const weight 	= getWidget(from_table, name_weight, form_num);

				// Get values for all the fields, but store placeholder values of the form id_n
				// where none is available because the Session object we're building wants to use
				// id's for indexes. We'll have to make sure before we submit that any such
				// placeholder values are removed. Because we are converting from a teams table
				// the unique id n is of a t.p format (so each performance and player has a unique
				// id placeholder)
				const default_id = id_prefix+form_num;
				const pID = getNumberValue(pid, default_id);
				const plID = getNumberValue(plid, default_id);
				const psVal = getNumberValue(pscore, null);
				const wVal = getNumberValue(weight, 1);

				pids.push(pID);
				plids.push(plID);
				weights.push(wVal);

				// Ranks and scores are special:
				//  ranks:
				// 	 as we build a player session each team player gets the rank of the team.
				//   (modellinga tie among those players in the player mode)
				//   This does not round trip perfectly. That is if the player session is edited
				//   that has ranked players, and this is converted to a teams session, only the
				//   one rank is conserved, and when converting back this is applied to all the
				//   players that were in that team.
				// scores:
				//   There's' a score widget for each player so these can be preserved. Individual
				//   player scores are summed when building teams, and when unpacking teams again
				//   if the pscore is still there we can use it. Othwerise we shoudl give each
				//   pscore on fraction of the rscore so when they are summed above they at least
				//   approximate a round trip sensibly.

				ranks.push(rVal);
				scores.push(Number.isInteger(psVal) && psVal > 0  ? psVal : rsVal ? Math.floor(rsVal/num_team_players) : null);

				// Rank IDs are provided by splitingt he team rank on & above.
				// BUT, Rank IDs may or may not be available (we ar egoing one team/rank
				// to many (one per player in the team).
				//
				// For example editing a team session and convgerting it to individual
				// there wa sone rank per team, and new each player needs a rank. So
				// if a rank ID is not available from rids above we add a placeholder
				// which will support round tripping (swithcig mode back and forth and
				// conserving data entered.
				//
				// Because Rank IDs are a hidden field we can pull this conserving trick
				// which we don't have available for ranks themselves or scores (as those)
				// fields are visible and so the conversion from player to teams summarises
				// the data per team and can't unwind it again to original if round tripping
				// back to individual.
				if (p>=rids.length) rids.push(id_prefix+form_num);
			}

			// If the sum of scores is not the same as the rscore, spread the remainder out among
			// first players just because (to maintain the rsVal = num_team_players * psVal identity)
			let sum_scores = scores.reduce((a, b) => a + b);
			if (rsVal && sum_scores < rsVal)
				for (let p=0; num_team_players-(rsVal-sum_scores); p++)
					scores[p] += 1;
			sum_scores = scores.reduce((a, b) => a + b);
			console.assert(sum_scores === rsVal, "Score distribution failed!")

			// Now push all the collected player info into the session data buckets
			for (let p=0; p<num_team_players; p++) {
				// Rank ID keyed items
				const rid = rids[p];
				rIDs.push(rid);
				ridRanks[rid] = rank.value;
				ridScores[rid] = scores[p];
				ridPlayers[rid] = plids[p];

				// Performance ID keyed items
				// In player mode scores are Rank associated and no perfromance associated scorers are used
				// Performance associated scores are only used if a game supports Team and Inidividual scoring.
				const pid =  pids[p];
				pIDs.push(pid);
				pidPlayers[pid] = plids[p];
				pidWeights[pid] = weights[p];
			}
		}

		session= session_dict(
					 team_play,
					 // Rank ID (rID) keyed dicts
					 rIDs, 			// Array of rank IDs
					 ridRanks,		// dict of ranks keyed on rID
					 ridScores,	    // dict of scores keyed on rID
					 ridPlayers,	// dict of player IDs keyed on rID
					 {}, 			// dict of team IDs keyed on rID
					 // Team ID (tID) keyed dicts
					 {}, 			// dict of team names keyed on tID.
					 {}, 			// dict of team player lists keyed on tID with list of player IDs as value
					 // Performance ID (pID) keyed dicts
					 pIDs,			// Array of performance IDs
					 pidPlayers, 	// dict of player IDs keyed on pID
					 {}, 			// dict of performance scores keyed on pID
					 pidWeights		// dict of performance weights keyed on pID
				);

		return reconcile_ranks(session);
	}
}

// Event handler for the row count changes, can respond to three types of change:
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
		for (let i = 0; i < event.target.value; i++) {
		    let boxNum = findChildByName(Table.parentNode, name_num_team_players.replace(form_number,i)); 	// This is the number of players in the team. Used only in form processing.

		    adjustTable(boxNum);
		}
	}
}

// Event handler for change of a selected player
// In Individual Play Mode, the player is identified in both a Rank object and a Performance Object.
// And so the form has to contain two widgets:
//		form.related_forms.Rank.player
//		form.related_forms.Performance.player
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
		const row = event.target.parentElement.parentElement;
		const player_copy = $$(player_copy_id, row);
		player_copy.value = event.target.value;
	}
}

// A DAL forward handler that returns the player PKs to exclude
function excludePlayers() {
	const pplayers = $$(id_tbl_visbl).querySelectorAll(qs_pplayers);
	let selected_players = [];
	for (player of pplayers)
		if (player.value)
			selected_players.push(player.value)
	const exclude = selected_players.join(",");
	//for (player of pplayers)
	//	player.attributes["data-autocomplete-light-url"].value = player.attributes["data-autocomplete-light-url"].value.split("?")[0] + "?exclude=" + exclude;
	return exclude;
}

// We have to register the DAL forward handler and can only do it after the DAL library has initialised
// which it does in a handler attached to "load". We atach ours after theirs and so yl is defined.
function registerForwarder() { yl.registerForwardHandler("Performance.player", excludePlayers); }
window.addEventListener("load", registerForwarder);

// Event hook if a score changes.
// OnSubmit handles removing hidden scores or ranks form
// the submission so there are no conflicts in the submission.
// If ranks are shown to break ties, when shoen they are
// initialised to reflect scores as best possible.
// What we do here is if all scores are entered and there is
// a tie, we show the TieBreakers checkbox, and
// if there are no ties, we hide it and the TieBreakers.
function OnScoreChange(event) {
	const id = event.target.id; // id_Rank-0-score or id_Performance-0-score
	const break_ties_switch = $$(id_show_tie_breakers);

	const is_rank_score = id.includes(rank_prefix);
	const is_perf_score = id.includes(performance_prefix);

	// Collect the session information from the visible table
	let session = collect_session_data()

	const have_rscores = show_rank_scores && Object.values(session["rScores"]).every(v => v!==null);
	const have_pscores = show_perf_scores && Object.values(session["pScores"]).every(v => v!==null);

	if (is_perf_score) {
		const entry_id = getEntryId(id);
		const team_id = getPart(1, entry_id);

		const same_team = new RegExp(`${id_prefix}${team_id}.\\d+`);
		const pscore_set = Object.keys(session["pScores"]).filter(id => same_team.test(id))


		/*
			pIDs: (4) ["id_0.0", "id_0.1", "id_1.0", "id_1.1"]
			pPlayers: {id_0.0: "id_0.0", id_0.1: "id_0.1", id_1.0: "id_1.0", id_1.1: "id_1.1"}
			pScores: {id_0.0: 4, id_0.1: 6, id_1.0: null, id_1.1: null}
			pWeights: {id_0.0: 1, id_0.1: 1, id_1.0: 1, id_1.1: 1}
			provided: trueshowhideTieBreakers_if_needed
			rIDs: (2) ["id_0&id_1", "id_2&id_3"]
			rPlayers: {}
			rRanks: {id_0&id_1: 1, id_2&id_3: 2}
			rScores: {id_0&id_1: null, id_2&id_3: null}
			rTeams: {id_0&id_1: "id_0", id_2&id_3: "id_1"}
			tTeamNames: {id_0: "Team 0", id_1: "Team 1"}
			tTeamPlayers: {id_0: Array(2), id_1: Array(2)}
		*/


		// TODO: If we have all the perf scores for a given rank score and lack the rank score
		// set the rank score to the sum of perf scores.
		debugger;
	}

	if (have_rscores) {
		manage_rank_ties(session); // Sets "show_tiebreakers"
		showhideRankScoreColumns(); // Acts on "show_tiebreakers"
	}

}

// Detect a rank ties, and if found make sure the break ties checkbox is shown
// and its status ()checked or otherwise) is respected.
function manage_rank_ties(session) {
	if (session === undefined) session = collect_session_data();

	const break_ties_switch = $$(id_show_tie_breakers);
	const unique_rscores = new Set(Object.values(session["rScores"]))
	const have_ties = unique_rscores.size < Object.values(session["rScores"]).length;
	const tie_breaker_controls = document.querySelectorAll(".tie_breaker");
	tie_breaker_controls.forEach(c => c.style.display = have_ties ? "table-cell" : "none");
	show_tiebreakers = have_ties && break_ties_switch.checked;
	if (show_tiebreakers) reconcile_ranks(); // if the tie_breakers column (ranks) is visible, reconcile the ranks
}

// Acts on the visible table (Team or Individual session)
// and examines the scores to see if ranks need adjusting
// as tie breakers.
function reconcile_ranks(session) {
	let display_result = false;
	if (session === undefined) {
		display_result = true;
		session = collect_session_data()
	}

	// If a session is provided (it's an update/edit form, then ranks were already reconciled)
	// and any tie breakers were added in the ranks if needed for scoring games. We don't want to
	// do it again and lose those manually entered tie breakers. This will be noted in the global
	// Session as Sessioni.provided. Quite distinct from the local session (which may have been
	// colected from the form elements and hence have tied scores which the reconsiler below will
	// give the same rank overwriting any ranks already enetered)
	if (!Session.provided) {
		// Produce a tie-gapped ranking from the scores
		// game_scoring will include either HIGH_SCORE_WINS or LOW_SCORE_WINS
		// We should never be asked to reconcile ranks for a NO_SCORES game
		const rscores = session["rScores"]
		const score_sorted_rids = sortObject(rscores, !game_scoring.includes("LOW_SCORE_WINS"))
		let i = 1;
		let prev_rank = 1
		let prev_score = -11
		console.log("Reconciling ranks:");
		for (let rid of score_sorted_rids) {
			const score = rscores[rid];
			const rank = (score === prev_score) ? prev_rank : i;
			console.log(`	${rid}	${score} => ${rank}`);
			session["rRanks"][rid] = rank;
			i++;
			prev_rank = rank;
			prev_score = score;
		}

		if (display_result) {
			const team_switch = $$(id_team_switch);
			const num_players = $$(id_num_players);
			const num_teams = $$(id_num_teams);

			adjustTable(team_switch.checked ? num_teams : num_players, session);
		}
	}

	return session;
}

// Event Handler for the showTieBreakers checkbox. If checked
// we display ranks as well scores. Else only scores.
// The ranks are (optionally) used to break ties.
// When we show them we intiialise them with a tie-gapped
// ranking as best possible with the scores available.
function showhideTieBreakers(event) {
    const checked = event.target.checked;
	show_tiebreakers = checked;
    if (show_tiebreakers) reconcile_ranks();
	showhideRankScoreColumns();
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

// Event handler for showing all ranks and scores fro debugging
function showhideRankScoreDebugging(event) {
    const checked = event.target.checked;
	debug_ranks_and_scores = checked;
	showhideRankScoreColumns();
}


// There are management forms for both Rank and Performance that must be included in the template.
// a la:
//			{{ form.related_forms.Rank.management_form }}
//			{{ form.related_forms.Performance.management_form }}
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
	// INITIAL is very relevant to "edit" forms as well, as when TOTAL is below INITIAL we need to
	// destroy Rank, Team or Performance objects (we've removed competitors from the ranking). These must
	// be flagged with a -DELETE element.

    const rinit  = findChildByName(div, name_rinit);
    const pinit  = findChildByName(div, name_pinit);
    const tinit  = findChildByName(div, name_tinit);
    const rtotal = findChildByName(div, name_rtotal);
    const ptotal = findChildByName(div, name_ptotal);
    let   ttotal = findChildByName(div, name_ttotal);

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
    const rdels = div.querySelectorAll(qs_rdels).length;
    const pdels = div.querySelectorAll(qs_pdels).length;
    const tdels = div.querySelectorAll(qs_tdels).length;

    if (div.id === id_indiv_div) {
    	const num_players = Number($$(id_num_players).value);
    	rtotal.value = num_players + rdels;
    	ptotal.value = num_players + pdels;

    	if (tdels>0) {
			/*
			   Individual forms don't typically have a management form for Teams.
			   But if a Teams form is loaded and then convered to an Individual form
			   there may be DELETE requests on teams added to this div during OnSubmit().
			   These need Management Form support. We expect the management form to be
			   in a div named "Team-Management-Form". We can copy it from the team form
			   inster it in the indiv form after the "Rank-Management-Form" and then set
			   the INITIAL_FORMS inputs to the count of tdels and TOTAL_FORMS to 0.
			*/
    		if (!ttotal){
				teams_div = document.getElementById(id_teams_div);
				rank_management_div = div.querySelector("div[name='Rank-Management-Form']");
				team_management_div = teams_div.querySelector("div[name='Team-Management-Form']").cloneNode(true); // Deep clone
				insertAfter(team_management_div, rank_management_div);
				ttotal = findChildByName(div, name_ttotal);
			}
    		ttotal.value = tdels;
    	}
    } else if (div.id === id_teams_div) {
    	const num_teams = Number($$(id_num_teams).value);
    	rtotal.value = num_teams + rdels;

    	let P = 0; // Total number of Players (Performances)
    	let T = 0; // Total number of Teams
		for (let t = 0; t < num_teams; t++) {
			// Add the number of players in Team t to the running total
	    	const id_table = 'tblTeamsBody' + t;
	    	const table = $$(id_table);
            const box_num_players = findChildByName(table, name_num_team_players.replace(form_number,t));
    		P += Number(box_num_players.value);

    		// If the team has a valid Team ID (is not blank or a placeholder inserted
    		// elsewhere for form management (in form id_n generally) the add 1 to the
    		// team count, other wise remove the team ID element (don't submit it).
	    	const real_name_tid = name_tid.replace(form_number,t);
	    	const tid = findChildByName(table, real_name_tid);
	    	if (tid != undefined && tid.value && !isNaN(tid.value)) T++;
        }
		ptotal.value = P + pdels;

    	ttotal.value = num_teams + tdels;

    	// tinit is special, because it should be the number of teams that have Team IDs
    	// which is from 0 to num_teams really because if we were editing a individual play
    	// mode session and converted to team mode they won't have IDs and if we're editing
    	// a team play session but add some teams those too won't have IDs. And tinit should
    	// be the number of teams that have IDs.
    	tinit.value = T;
    }
}

function insertErrors() {
// Errors if any are provided in the global related_form_errors
// These are provided if a formwm as submitted, failed validation
// and rerenders with the indent of feeding back error information.
//
// It's a dict, and we want the Rank and performance entries if
// they exist. The value will be a list, with one entry per form
// in the formset.

// In individual mode, we have one row per Rank and Performance
// inside a table with ID based on tblPlayersTable.

// In Team mode with one row per team rank and one per player
// performance under it. So Rank freedback goes above a team
// Rank row in tblTeamsTable and player Performance feedback
// above a Performance row in tblTeamPlayersTable.

// We can genralise this by searching for the Rank widget and the TR
// its in and instering a tR before it with amessage if there's a
// message and doing same for a Performance widget (Player name)
	if (related_form_errors) {
		if (related_form_errors.hasOwnProperty("Performance")) {
			// Look for id "Performance-n-player"
			for (let i = 0; i < related_form_errors.Performance.length; i++) {
				const n_errors = Object.keys(related_form_errors.Performance[i]).length
				if ( n_errors > 0) {
					const id = id_player.replace(form_number, i);
					const row = $(`#${id}`).closest('tr');
					for (let j in related_form_errors.Performance[i]) {
				    	const new_row = $(`<tr class="error"><td colspan=10>Performance error: ${related_form_errors.Performance[i][j]}</td></tr>`);
				    	new_row.insertBefore(row);
					}
				}
			}
		}

		if (related_form_errors.hasOwnProperty("Rank")) {
			// Look for id "Rank-n-rank"
			for (let i = 0; i < related_form_errors.Rank.length; i++) {
				const n_errors = Object.keys(related_form_errors.Rank[i]).length
				if ( n_errors > 0) {
					const id = id_rank.replace(form_number, i);
					const row = $(`#${id}`).closest('tr');
					for (let j in related_form_errors.Rank[i]) {
				    	const new_row = $(`<tr class="error"><td colspan=10>Rank error: ${related_form_errors.Rank[i][j]}</td></tr>`);
				    	new_row.insertBefore(row);
					}
				}

			}
		}
	}
}

function add_player(select2, player_id) {
	// Adds a player to a select Django-auto-complete-light select2 widget

	// Populating the select2 widget from django-auto-complete-light is not so
	// trivial, and taken from here:
	// 		https://select2.org/programmatic-control/add-select-clear-items#preselecting-options-in-an-remotely-sourced-ajax-select2

	if (Number(player_id)) {
	    const url = player_selector_url.replace(/\d+$/, player_id)

	    $.ajax({
	        type: 'GET',
	        url: url
	    }).then(function (data) {
	        // create the option and append to Select2
	        var option = new Option(data, player_id, true, true);
	        select2.append(option).trigger('change');

	        // manually trigger the `select2:select` event
	        select2.trigger({
	            type: 'select2:select',
	            params: {
	                data: data
	            }
	        });
	    });
	}
}

// Given a session object and a table row of specified type will force the widgets in that
// row to conform with the session object.
function applySessionToRow(session, row, table_type) {
    // Select the values we'll use for those widgets
    const rids 			= (session && "rIDs" in session) 		 ? session["rIDs"] 		   : [];
    const ranks 		= (session && "rRanks" in session) 		 ? session["rRanks"]	   : {};
    const rscores 		= (session && "rScores" in session) 	 ? session["rScores"] 	   : {};
    const rplayers 		= (session && "rPlayers" in session) 	 ? session["rPlayers"] 	   : {};

    const pids 			= (session && "pIDs" in session) 		 ? session["pIDs"] 		   : [];
    const pplayers 		= (session && "pPlayers" in session) 	 ? session["pPlayers"] 	   : {};
    const pscores 		= (session && "pScores" in session) 	 ? session["pScores"] 	   : {};
    const weights 		= (session && "pWeights" in session) 	 ? session["pWeights"] 	   : {};

    const teams 		= (session && "rTeams" in session) 		 ? session["rTeams"] 	   : {};
    const teamnames 	= (session && "tTeamNames" in session) 	 ? session["tTeamNames"]   : {};
    const teamplayers 	= (session && "tTeamPlayers" in session) ? session["tTeamPlayers"] : {};

	const pidRIDs       = (session && "pRIDs" in session) 		 ? session["pRIDs"] 	   : {};

    // The row element contains an entry id that is useful for some defaults if session data is missing
    const entry_id = getEntryId(row.id);

    switch (table_type) {
    	case TableType.Players: {
    	    const rid 			= getWidget(row, name_rid);        // This is the ID of the rank entry in the database. Needed when editing sessions (and the ranks associated with them)
    	    const pid 			= getWidget(row, name_pid);        // This is the ID of the performance entry in the database. Needed when editing sessions (and the ranks associated with them)
    	    const rank 			= getWidget(row, name_rank);       // This is the rank itself, a dango field for generic processing, but with a default value added when created here as well
    	    const player 		= getWidget(row, name_player);     // This is the name/id of the player with that rank, a dango field for generic processing
    	    const player_copy 	= getWidget(row, name_player_copy);// This is a copy of the player we need to keep of player (see header for details)
    	    const rscore 		= getWidget(row, name_rscore);     // In Individual mode each rank has a score, performances need no score
    	    const weight 		= getWidget(row, name_weight);     // This is the partial play weighting

    	    const perf_id 	    = entry_id < pids.length ? pids[entry_id] 	 : "";
    	    const player_id 	= perf_id in pplayers 	 ? pplayers[perf_id] : "";
			const weight_value  = perf_id in weights     ? weights[perf_id]  : 1;

    	    const rank_id 	    = pidRIDs[perf_id];
			const rank_value 	= rank_id in ranks ? ranks[rank_id] : Number(entry_id)+1;
    	    const player_id2 	= rank_id in rplayers 	 ? rplayers[rank_id] : "";
			const rscore_value  = rank_id in rscores     ? rscores[rank_id]  : "";

			console.assert(player_id == player_id2, `Session data seems corrupt. Performance and Rank Player IDs not in agreement (${player_id} ≠ ${player_id2}).`);

            rid.value 	 = rank_id
            rank.value 	 = rank_value;
            player.value = player_id;
            pid.value 	 = perf_id;
            rscore.value = rscore_value;
            weight.value = weight_value;
            player_copy.value = player_id;

			// Set the value of the select2 widget for player
            const select2_player = $("#"+$.escapeSelector(player.id), row)
            add_player(select2_player, player_id)

            // Set the Rank score visibility as requested (global set by game and team_play options)
            if (debug_ranks_and_scores) {
	            getParent(rank, 'TD').style.display   = "table-cell";
	            getParent(rscore, 'TD').style.display = "table-cell";
			} else {
	            getParent(rank, 'TD').style.display   = (show_rank_scores && !show_tiebreakers) ? "none" : "table-cell";
	            getParent(rscore, 'TD').style.display = show_rank_scores ? "table-cell" : "none";
	        }
    	}
    	break;

    	case TableType.Teams: {
            const rid 			= getWidget(row, name_rid);        // This is the ID of the rank entry in the database. Needed when editing sessions (and the ranks associated with them)
            const rank 			= getWidget(row, name_rank);       // This is the rank itself, a dango field for generic processing, but with a default value added when created here as well
            const rscore 		= getWidget(row, name_rscore);     // This is the score for that rank if supported
            const tid 			= getWidget(row, name_tid);        // This is the team ID if we're editing a team session
            const teamname 		= getWidget(row, name_team_name);  // This is the name of the team. Optional in the database and it an stay a local field for specific (non-generic) processing when submitted.

            rid.value 	 	= entry_id < rids.length ? rids[entry_id] 		: "";
            rank.value 	 	= rid.value in ranks 	 ? ranks[rid.value] 	: Number(entry_id)+1;
            rscore.value 	= rid.value in rscores 	 ? rscores[rid.value] 	: "";
            tid.value 	 	= rid.value in teams 	 ? teams[rid.value] 	: "";
            teamname.value 	= tid.value in teamnames ? teamnames[tid.value] : "Team " + (Number(entry_id)+1);

            const num_players = getWidget(row, name_num_team_players);
            const tID = tid.value;

            num_players.value = (tID in teamplayers && entry_id < teamplayers[tID].length) ? teamplayers[tID].length : game_min_teams;
			num_players.defaultValue = num_players.value;

            // Set the Rank score visitbility as requested (global set by game and team_play options)
            if (debug_ranks_and_scores) {
	            getParent(rank, 'TD').style.display   = "table-cell";
	            getParent(rscore, 'TD').style.display = "table-cell";
			} else {
		        getParent(rank, 'TD').style.display   = (show_rank_scores && !show_tiebreakers) ? "none" : "table-cell";
		        getParent(rscore, 'TD').style.display = show_rank_scores ? "table-cell" : "none";
		    }
    	}
		break;

    	case TableType.TeamPlayers: {
    	    const pid 			= getWidget(row, name_pid);        // This is the ID of the performance entry in the database. Needed when editing sessions (and the ranks associated with them)
    	    const player 		= getWidget(row, name_player);     // This is the name/id of the player with that rank, a dango field for generic processing
    	    const pscore 		= getWidget(row, name_pscore);     // This is the performance score, only needed if Individual scores a requested in Team mode
    	    const weight 		= getWidget(row, name_weight);     // This is the partial play weighting, a dango field for generic processing

    		const rownum_Team 	  	= getPart(1, entry_id);
            const rownum_TeamPlayer = getPart(2, entry_id);

            // Find Player ID first so we can use it to find the index into the Weights and pID lists
            const rID = rownum_Team < rids.length ? rids[rownum_Team] : undefined;
            const tID = rID in teams ? teams[rID] : undefined;

    	    const player_id 	= tID in teamplayers ? teamplayers[tID][rownum_TeamPlayer] : "";

			// Performance id's a a tad harder here:
			const pID = Object.keys(pplayers).find(key => pplayers[key] == player_id);

			// Assign the performance id to the pid form element.
            pid.value 	 = pID != undefined ? pID : "";

			// Add the player to the player selector widget
            const select2_player = $("#"+$.escapeSelector(player.id), row)
            add_player(select2_player, player_id)

			//This is what we do for a standard select widget (vs. select2)
            //player.value = tID in teamplayers 		? teamplayers[tID][rownum_TeamPlayer] : "";

			// Add the performance score and partial playweighting
            pscore.value = pID in pscores ? pscores[pID] : "";
            weight.value = player_id in weights ? weights[player_id] : 1;

            // Set the Performance score visitbility as requested (global set by game and team_play options)
            if (debug_ranks_and_scores) {
	            getParent(pscore, 'TD').style.display = "table-cell";
			} else {
	            getParent(pscore, 'TD').style.display = (show_perf_scores ? "block" : "none");
	        }
    	}
        break;
    };

    return row;
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
	const table_type = (template.id === "templatePlayersTable") ? TableType.Players
			         : (template.id === "templateTeamsTable")   ? TableType.Teams
			         : (template.id === "templateTeamPlayersTable") ? TableType.TeamPlayers
			         : 0;

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
    let rowsNeeded = (table_type == TableType.Teams ? 2*entries : entries) + 1;
    let rowsPresent = table.rows.length;

    // If there are rows in the table already, and we have session data, we
    // should really check all present rows for conformance with the provided
    // session data. This is particularly relevant when switching between modes
    // (individual and team play for example and back again etc, as prior to
    // rendering the table we build session data from from the visible form
    // and pass it into this rendering routine. And the session data may
    // have imposed changes on the data (this is especially relevant with
    // ranks as a move from team play to individual play imposes ranks from
    // the teams table onto the new players table).
    //
    // We need to work out the step size though as a players table has
    // a player every row, a teams table has a team on every second row.
    if (session) {
	    const step = table_type == TableType.Teams ? 2 : 1;

	    for (let i = 1; i < rowsPresent; i += step) {
	    	const row = table.rows[i];

	    	applySessionToRow(session, row, table_type);
	    }
    }

    // Now remove or add rows as needed
    if (rowsNeeded < rowsPresent) {
    	// Move the excess rows to the trash (whence we can fetch them again if needed)
    	// Never remove them all though. 0 entries not supported. The trash is FILO
    	// queue in that we append entries as we remove them and then pull them off
    	// the top again when needed.
        if (entries > 1) {
        	let chop = rowsPresent - rowsNeeded;
        	if (table_type == TableType.Teams) chop = chop/2;

	        for (let i = 0; i < chop; i++) {
	        	const last_row = table.rows[table.rows.length - 1];
	        	trash.appendChild(last_row);

	        	if (table_type == TableType.Teams) {
		        	const last_row = table.rows[table.rows.length - 1];
		        	trash.appendChild(last_row);
	        	}
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
        // On a teams table we add them in pairs so need half the steps
        // (TeamsBody and TeamsDetail) - rowsNeeded was set to twice the
        // number of new entries above when it's a teams table.
        const steps = table_type == TableType.Teams ? (rowsNeeded - rowsPresent) / 2 : rowsNeeded - rowsPresent;

        for (let i = 0; i < steps; i++) {
            // Build an entry ID, which is just an integer representing the row for
            // either Players in Individual Play mode or Teams in Team Play mode. But for
            // Players in Team Play mode it will be a composite number of form "team.player"
        	const body_rows = rowsPresent > 0 ? rowsPresent - 1 : 0;
        	const entry_id = (table_type == TableType.TeamPlayers ? (entry_number + '.') : 0)
        				   + ((table_type == TableType.Teams ? body_rows/2 : body_rows) + i);

        	// If it's a teams we need to pop two items off trash, else only one
        	const have_trash = trash.rows.length >= (table_type == TableType.Teams ? 2 : 1);

        	if (have_trash) {
	        	const last_row = trash.rows[trash.rows.length - 1];
	        	table.appendChild(last_row);

	        	if (table_type == TableType.Teams) {
		        	const last_row = trash.rows[trash.rows.length - 1];
		        	table.appendChild(last_row);
	        	}
        	} else {
	        	// Copy the Body TR element from the template
	            const TRB = trb.cloneNode(true);
	            TRB.id = trb.id.replace("template", "tbl") + entry_id;
	            TRB.className = trb.className;
	            TRB.style = trb.style;

	            // Now fix all the widget names (form template names to entry specific names)
	            // Not all these widgets are expected for every table_type of course.
	            // Those not present are just ignored. This us a superset of both table types.
	            fixWidget(TRB, name_rid, entry_id);        // This is the ID of the rank entry in the database. Needed when editing sessions (and the ranks associated with them)
	            fixWidget(TRB, name_pid, entry_id);        // This is the ID of the performance entry in the database. Needed when editing sessions (and the ranks associated with them)
	            fixWidget(TRB, name_rank, entry_id);       // This is the rank itself, a dango field for generic processing, but with a default value added when created here as well
	            fixWidget(TRB, name_player, entry_id);     // This is the name/id of the player with that rank, a django field for generic processing
	            fixWidget(TRB, name_player_copy, entry_id);// This is a copy of the player we need to keep of player (see header for details)
	            fixWidget(TRB, name_rscore, entry_id);     // This is the rank score if needed
	            fixWidget(TRB, name_pscore, entry_id);     // This is the performance score if needed
	            fixWidget(TRB, name_weight, entry_id);     // This is the partial play weighting, a dango field for generic processing
	            fixWidget(TRB, name_tid, entry_id);        // This is the team ID if we're editing a team session
	            fixWidget(TRB, name_team_name, entry_id);  // This is the name of the team. Optional in the database and it an stay a local field for specific (non-generic) processing when submitted.

	            // And if there's a team player count widget we need to fix that too
	            fixWidget(TRB, name_num_team_players, entry_id);

	            // Then apply the session data to the widgets in the TR element
	            applySessionToRow(session, TRB, table_type);

	        	// Then enable all the widgets (disabled in the template by default)
	            enableChildren(TRB, true);

	            // And add the new TR to the displayed table
	            table.appendChild(TRB);

	            // Add the second row, the (empty) Detail row if needed for added Teams
	            // This is where we willplays  a TeamPlayers table later (in fact by calling
	            // this very rendering routine again for the TeamPlayers table).
	            if (table_type == TableType.Teams) {
	                const trd = $$(template.id.replace("Table", "Detail"));
	                const TRD = trd.cloneNode(true);
	                TRD.id = trd.id.replace("template", "tbl") + entry_id;

	                const TCDid = trd.id.replace("template", "tbl") + "Cell" + entry_id;
	                TRD.children[0].id = TCDid;

	                table.appendChild(TRD);
	            }

	            // And finally, once the row is in the DOM, the DAL widgets used for players can have a
	            // forward configuration and if so it's in a sibling div of class dal-forward-conf and needs
	            // fixing too.
	            // See: https://django-autocomplete-light.readthedocs.io/en/master/tutorial.html#customizing-forwarding-logic
	            const player_id = id_player.replace(form_number, entry_id);
	            const forward_conf = $(`#${player_id} ~ div.dal-forward-conf`);
	            const id_template = forward_conf.attr('id');
	            forward_conf.attr('id', id_template.replace(form_number, entry_id));
        	}
        }
    }

    // Update the Django Management forms (and tabindices)
    updateManagementForms(getParent(table, 'DIV'));

    insertErrors();

    // Return the table that was drawn
    return(table);
}

// Given a HTML element with a value will adjust the associated
// table to the number of rows specified in that value.
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
// table with. A map is defined from the holding-table to
// template-table.
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

    // Determine which session data to use (if none supplied use the Global set on edits and nothing on adds)
    if (!session && Session.provided) session = Session;

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

    // const is_players 		= (template.id === "templatePlayersTable");
    const is_teams 			= (template.id === "templateTeamsTable");
    const is_teamplayers 	= (template.id === "templateTeamPlayersTable");

	// team_players are special in that they don't become siblings of the tmeplte
	// they have to go in cell of the Teams table that did.
    const placein = is_teamplayers ? $$(tr.id.replace("Body","DetailCell")): template.parentNode;

    // If the value is an integer (string of digits) then process it
    if (element.value.match(/^\d+$/)) {
    	// The minimum and maximum number of players  or teams are game properties (globally available)
        const minEntries = is_teamplayers ? game_min_players_per_team : is_teams ? game_min_teams : game_min_players;
        const maxEntries = is_teamplayers ? game_max_players_per_team : is_teams ? game_max_teams : game_max_players;

        // The number of teams or players being requested, with a minimum and maximum enforced
        const num = Number(element.value);
        const numEntries = num < minEntries ? minEntries : num > maxEntries ? maxEntries : num;

        // If the value was changed (exceeded bounds) change it back!
        if (numEntries != num) element.value = numEntries;

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

// Switches which div (tems or individual play mode) is displayed
// and leaves a global flag to indicate which.
function showDiv(which_one) {
	if (which_one === "teams" ) {
		id_visbl_div = id_teams_div;
		id_tbl_visbl = id_tbl_teams;

		showhideRankScoreColumns(id_visbl_div);

		$$(id_indiv_div).style.display = 'none';
		$$(id_teams_div).style.display = 'block';

    	enableChildren($$(id_indiv_div), false);
    	enableChildren($$(id_teams_div), true);
	} else if (which_one === "indiv" ) {
		id_visbl_div = id_indiv_div;
		id_tbl_visbl = id_tbl_players;
		showhideRankScoreColumns(id_visbl_div);


		$$(id_teams_div).style.display = 'none';
		$$(id_indiv_div).style.display = 'block';

    	enableChildren($$(id_teams_div), false);
    	enableChildren($$(id_indiv_div), true);
	}
}

// Enable or disable a control and all its children
function enableChildren(of, enable) {
	if ((/^template/).test(of.id)) return;  // Don't fix a template only a clone that's been renamed

    of.disabled = (enable === undefined) ? true : !enable;

    const children = of.children;
    for (let i = 0; i < children.length; i++)
    	enableChildren(children[i], enable);
}

//Get the Django widget with a give name inside a given element
function getWidget(inside, name, entry_id) {
	if (entry_id == undefined) {
        // We expect an element which has a form_number in it somewhere but we don't know
		// what number. So if there is a form_number in there, we'll use a querySelector
		// to find the first element that matches the pattern.
		if (name.includes(form_number)) {
			const re = new RegExp("^(.*?)" + form_number + "(.*?)$");
		    const matches = name.match(re);
			return inside.querySelector("[name^='" + matches[1] + "'][name$='" + matches[2] + "']");
		} else {
			return findChildByName(inside, name);
		}
	} else {
		return findChildByName(inside, name.replace(form_number, entry_id));
	}
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

	try {
		return element.querySelector("[name='" + name + "']");
	} catch (err) {
		debugger;
	}
}

// Get the parent of an element of a given type
function getParent(of, type) {
    let parent = of;
    do {
        parent = parent.parentNode;
    } while (parent.tagName !== type && parent !== document);
    return parent;
}

//Get the row id from an id or name string. e.g. ThisisRow4 -> 5
function getEntryId(of) {
    const matches = String(of).match(/^.*?([\d\.]+).*?$/);
    return matches == null ? "" : matches[1];
}

//Get the form number from a name in the format Model-FormNumber-FieldName
function getFormNumber(of) {
    const matches = String(of).match(/^.*?\-?(\d+)\-?.*?$/);
    return matches == null ? "" : matches[1];
}

// Get part 1 or 2 of an n.m string
function getPart(part, of) {
    const matches = String(of).match(/^(\d+)\.(\d+)$/);
    return matches == null ? "" : matches[part];
}

// Get the value of an element if it is a number, else a specifed default
function getNumberValue(element, default_value) {
	return (element == undefined || element.value === '' || isNaN(element.value)) ? default_value : Number(element.value);
}

//Given a Django widget will, check if it is for the "from" form and if so set
//its name to "to" form number, leaving the id intact.
//Used to renumber forms in the form submission.
function renameDjangoWidget(element, from, to) {
	const django_widget = new RegExp(`^${id_prefix}(.+?)\\-(\\d+)\\-(.+?)$`)
	 const matches = String(element.id).match(django_widget);
	 if (matches != null && Number(matches[2]) == from)
	 	element.name = matches[1] + "-" + to + "-" + matches[3];
}

// Map element names from one form number to another for the the Django models specified in tthe list
function mapElementNames(container, models, from, to) {
	if (from != to)
		for (let m=0; m<models.length; m++) {
		    const elements = container.querySelectorAll("[id^='"+id_prefix+models[m]+"-"+from+"']");

		    for (let e=0; e<elements.length; e++)
		    	renameDjangoWidget(elements[e], from, to);
		}
}

// Insert a node just after a reference node (Javascript has a native insertBefore, but not insertAfter)
function insertAfter(newNode, referenceNode) {
    referenceNode.parentNode.insertBefore(newNode, referenceNode.nextSibling);
}

function $$(id, context) {
//  return document.getElementById(id);
//  but in that context or using jQuery (with an optional context for finding elements not in the document yet):
	if (context == undefined)
		return $('#'+	id)[0];
	else
		return $('#'+	id, context)[0];
}

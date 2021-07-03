// The basic Javascript to request and  generate a leaderboard

// Function to return useful metrics on the leaderboards (for layout of multiple boards) 
function leaderboard_metrics(LB, show_baseline) {
	const iSnaps = 5; // The index in the game tuple that tells us if the data is a leaderboard or list of snapshots
	const iHide  = 6; // The index in the game tuple that tells us if the last snapshot shoudl be hidden (is just a baseline)
	const iGameData =  7; // The index in the game tuple that holds data (snapshots (r a leaderboard)

	// The metrics we want to return
	let boardcount = LB.length; // The number of games we are displaying
	
	let maxshots = 0;			// We want to discover the widest game (maxium number of snapshots)
	let totalshots = 0;			// The total nbumber of snapshots we'll be displaying
	let boardshots = [];		// The number of snapshots in each board
	
	for (let g=0; g<boardcount; g++) {
		const has_snaps = LB[g][iSnaps];
		const has_hidden_baseline = LB[g][iHide];
		const delivered = has_snaps ? LB[g][iGameData].length : 1; // A leaderboard represents a single snapshot
		const hide = (use_baseline && has_hidden_baseline && !show_baseline ? 1 : 0);
		const snapshots = delivered - hide;
		if (snapshots > maxshots) maxshots = snapshots;
		totalshots += snapshots;
		boardshots[g] = snapshots;
	}	 
	
	return [boardcount, maxshots, totalshots, boardshots];
}

// Function to draw one leaderboard table
function LeaderboardTable(LB, snapshot, links, opts, selected_players, name_format, diagnose) {
/*
	LB is specific to one game and is a data structure that contains one board
	per snapshot, and each board is a list of players.

		In LB:
		First tier (game_wrapper) has just five values: 
			Game PK, 
			Game BGGid, 
			Game name,
			Game play count,
			Game session count,
			Snap (true if next entry is snapshots, false if next entry is leaderboard)
			Hide (true if the last snapshot shoudl be hidden, is just a baseline) 
			Leaderboard (being a ranked list of players + data) or Snapshots (being a list of snapshots)
	
		Optional Second tier (session wrapper) contains the snapshots which is a list of five-value tuples containing: 
			Session PK
			Date time string, 
			count of plays, 
			count of sessions, 
			session details
			Leaderboard (being a ranked list of players + data)
			A diagnostic leaderboard if needed
	
		Second or Third tier (player list) is the Leaderboard which is a list of tuples which have six values: 
			Player PK, 
			Player BGGid, 
			Player name, 
			Trueskill rating, 
			Play count,
			Victory count
	
	snapshot: 		  an integer, index into the list of Snapshots (being which snapshot to render)
	links:	  		  a string, either "BGG" or "CoGs" which selects what kind of links to use
	opts:  	  		  a list of flags (true/false) requesting specific rendering features
	selected_players: a list of players to highled if the highlight_selected option is on.
	name_format:	  a string, either "nick", "full" or "complete"    
*/
	if (diagnose == undefined) diagnose = false;
	
	// Column Indices in LB (game wrapper):
	const iPKgame = 0;
	const iBGGid = 1;
	const iGameName = 2;
	const iTotalPlays = 3;
	const iTotalSessions = 4;
	const iSnaps = 5;
	const iHide = 6;
	const iGameData = 7;
	
	// Column Indices in session wrapper
	const iSessionData = 8;
	
	// Options
	const [	highlight_players,
			highlight_changes,
			highlight_selected,
			details,
			analysis_pre,
			analysis_post,
			show_d_rank,
			show_d_rating,
			show_baseline ] = opts;
			
	// Extract the data we need
	const pkg            = LB[iPKgame];
	const BGGid          = LB[iBGGid];
	const game           = LB[iGameName];
	const game_plays     = LB[iTotalPlays];
	const game_sessions  = LB[iTotalSessions];
	const snaps          = LB[iSnaps];
	const hide           = LB[iHide] && !show_baseline;

	// A horendous hack but for now we determine if there's a session wrapper by checking the first element of the 
	// Game data (or the firts snap in the game data). This will be a PK if it's  session wrapper, but will be a 
	// tuple if the game data is a player list. 
	const test_element  = snaps ? LB[iGameData][0][0] : LB[iGameData][0];
	const session_wrapper = !Array.isArray(test_element); 

	let session = session_wrapper ? {} : null;
	
	// Fetch the player list
	let player_list = null;
	if (snapshot != null && snaps) {
		const count_snaps = LB[iGameData].length;
		
		// Return nothing if:
		// 	snapshot is too high (beyond the last snapshot, >= count_nsaps)  
		// 	snapshot is too low (before the first snapshot, < 0)
		//	the snapshot is a baseline that we should hide (snapshot >= count_snaps-1 && hide)
		if (snapshot >= count_snaps || snapshot < 0 || (hide && snapshot >= count_snaps-1)) return null;

		if (session) {		 
			// This MUST align with the way ajax_Leaderboards() bundles up leaderboards
			// which in turn relies on Game.leaderboard to provide its tuples.
			//
			// Rather a complex structure that may benefit from some naming (rather than
			// being a list of lists of lists of lists. Must explore how dictionaries
			// map
			// into Javascript at some stage and consider a reimplementation.
			
			// We cannot provide a diagnosis board if none is included
			// +2 because iSessionData is the index of the data item in the session wrapper.
			// .length returns one more, that is if iSessionData is 8 then then .length is 9.
			// This is the expected count. We expect a diagnostic board then at position 9
			// and if the .length is not (at least) 10 then we don't have a diagnostic board. 
			// To with 8+2 is 10. We check if lengths is less than 10 or iSessionData+2
			if (LB[iGameData][snapshot].length < iSessionData+2) diagnose = false;
			
			// Column Indices in LB[iSnapshots]:
			const iSessionPK           = 0;
			const iDateTime            = 1;
			const iPlayCount           = 2;
			const iSessionCount        = 3;
			const iSessionPlayers      = 4;
			const iSessionDetails      = 5;
			const iSessionAnalysisPre  = 6;
			const iSessionAnalysisPost = 7;
			const iPlayerList          = diagnose ? 9 : 8;
				
			// HTML values are let not const because we'll wrap selective contents with
			// links later
			// HTML values come paired with data values (which are ordered player list)
			session.pk                 = LB[iGameData][snapshot][iSessionPK]
			session.date_time          = LB[iGameData][snapshot][iDateTime]
			session.play_count         = LB[iGameData][snapshot][iPlayCount];
			session.session_count      = LB[iGameData][snapshot][iSessionCount];
			session.players            = LB[iGameData][snapshot][iSessionPlayers];
			session.details_html       = LB[iGameData][snapshot][iSessionDetails][0];
			session.details_data       = LB[iGameData][snapshot][iSessionDetails][1];
			session.analysis_pre_html  = LB[iGameData][snapshot][iSessionAnalysisPre][0];
			session.analysis_pre_data  = LB[iGameData][snapshot][iSessionAnalysisPre][1];
			session.analysis_post_html = LB[iGameData][snapshot][iSessionAnalysisPost][0];
			session.analysis_post_data = LB[iGameData][snapshot][iSessionAnalysisPost][1];
			
			session.link 			    = url_view_Session.replace('00',session.pk);
			
			player_list                = LB[iGameData][snapshot][iPlayerList];
		} else
			player_list                = LB[iGameData][snapshot];
	} else
		player_list                = LB[iGameData];
	
	// use_baseline is a global config
    // If we are using a baseline it is the last snapshot. If we are rendering it
	// which normally we wouldn't, but can be requested, then showing a delta is 
	// meaningless. As the show_d settings are consts above, we use hide_d settings 
	// to override them on this specific player list (snapshot, leaderboard) 	
	let hide_d_rank = (use_baseline && snapshot == LB[iGameData].length-1) || diagnose;
	let hide_d_rating = (use_baseline && snapshot == LB[iGameData].length-1) || diagnose;
	
	// Check if we have previous ranks or ratings provided
	// As these are provided programmatically we'll be conservatine here and if any one rank or rating
	// happens to missing we'll hide them (to ) preven a JS error trying to access it later). A failsafe.
	const iRankPrev = 13;			// index into player_list tuples of the previous rank if it's provided
	let have_previous_ranks = true; // Assume we have them
	for (let i = 0; i < player_list.length; i++)
		if (player_list[i].length <= iRankPrev) {
			have_previous_ranks = false; 
			break; 
		}

	const iRatingPrev = 14;			// index into player_list tuples of the previous rating  if it's provided
	let have_previous_ratings = true; // Assume we have them
	for (let i = 0; i < player_list.length; i++)
		if (player_list[i].length <= iRatingPrev) {
			have_previous_ratings = false; 
			break; 
		}
	
	// If we have no previous ranks or ratings we can't show the delta column!
	if (!have_previous_ranks) hide_d_rank = true;
	if (!have_previous_ratings) hide_d_rating = true;
		
	// Create the Game link based on the requested link target
	const linkGameCoGs = url_view_Game.replace('00',pkg);
	const linkGameBGG = "https:\/\/boardgamegeek.com/boardgame/" + BGGid;
	const linkGame = links == "CoGs" ? linkGameCoGs : links == "BGG" ?  linkGameBGG : null;

	// Fix the session detail and analysis headers which were provided with
	// templated links
	const linkPlayerCoGs = url_view_Player.replace('00','{ID}');
	const linkPlayerBGG = "https:\/\/boardgamegeek.com/user/{ID}";
	const linkTeamCoGs = url_view_Team.replace('00','{ID}');
	
	let linkRanker = {};
	linkRanker["Player"] = links == "CoGs" ? linkPlayerCoGs : links == "BGG" ?  linkPlayerBGG : null;
	linkRanker["Team"] = links == "CoGs" ? linkTeamCoGs : links == "BGG" ?  null : null;

	// Markup the session details with links
	if (session) {
		// Build a map of PK to BGGid for all rankers
		// Note, session.details_data, session.analysis_pre_data and
		// session.analysis_post_data perforce
		// contain the same map (albeit in a different order) so we can use just one
		// of them to build the map.
		let linkRankerID = {}
		for (let r = 0; r < session.details_data.length; r++) {
			const PK = session.details_data[r][0];
			const BGGname = session.details_data[r][1];
			
			linkRankerID[PK] = links == "CoGs" ? PK : links == "BGG" ?  BGGname : null;
		}

		// A regex replacer which has as args first the matched string then each of
		// the matched subgroup.s
		// The subgroups we expect for a link update to the HTML headers are
		// klass, model, id and then the text.
		// This is a function that the following replace() functions pass matched
		// groups to and is tasked with returning a the replacement string.
		function fix_template_link(match, klass, model, id, txt) {
			if (linkRankerID[id] == null) 
				return txt;
			else {
				const url = linkRanker[model].replace('{ID}', linkRankerID[id]);
				return "<A href='"+url+"' class='"+klass+"'>"+txt+"</A>";
			}
		}
		
		// Fix the links in the HTML headers
		// An example: {link.field_link.Player.1}Bernd{link_end}
		session.details_html       = session.details_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
		session.analysis_pre_html  = session.analysis_pre_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
		session.analysis_post_html = session.analysis_post_html.replace(/{link\.(.*?)\.(.*?)\.(.*?)}(.*?){link_end}/mg, fix_template_link);
	}
		
	// A regex replacer which has as args first the matched string then each of
	// the matched subgroups
	// The subgroups we expect from name update to the HTML headers are:
	// pk, nick, full, complete
	// We don't actually need the PK, it's just there.
	function fix_template_name(match, pk, nick, full, complete) {
	    switch (name_format) {
	      case "nick": return nick;
	      case "full": return full;
	      case "complete": return complete;
	      default: throw new Error ("Illegal name selector.");
	    }
	}

	// Fix the names in the HTML headers
	// An example: "{1,Bernd,Bernd <Hidden>,Bernd <Hidden> (Bernd)}"
	if (session) {
		session.details_html       = session.details_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
		session.analysis_pre_html  = session.analysis_pre_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
		session.analysis_post_html = session.analysis_post_html.replace(/{(\d+),(.+?),(.+?),(.+?)}/mg, fix_template_name);
	}
	
	// Define the number of columns in the board
	let lb_cols = 5;
	if (show_d_rank && !hide_d_rank) lb_cols++;
	if (show_d_rating && !hide_d_rating) lb_cols++;
	
	const table = document.createElement('TABLE');
	table.className = 'leaderboard'

	// Five header rows as follows:
	// A full-width session detail block, or the date the leaderboard was set
	// (of last session played that contributed to it)
	// A full-width pre session analysis
	// A full-width post session analysis
	// A game header with the name of the game (2 cols) and play/session summary
	// (3 cols)
	// A final header with 5 column headers (rank, player, rating, plays,
	// victories)

	const tableHead = document.createElement('THEAD');
	table.appendChild(tableHead);	    

	// #############################################################
	// First Header Row: The Game!
	
	const name_cols = 3;
	
	let tr = document.createElement('TR');
	tableHead.appendChild(tr);

	let th = document.createElement('TH');
	let content;
	
	// ****** The Game Name
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
	th.colSpan = name_cols;
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	// ****** The Game Play Count
	th = document.createElement('TH');
	plays = document.createTextNode((session ? session.play_count : game_plays) + " plays in "); 
	th.appendChild(plays);   

	// ****** The Game Play Count (Sessions)
	const sessions = (session ? session.session_count : game_sessions) + " sessions";
	if (links == "CoGs") {
		content = document.createElement('a');
		content.setAttribute("style", "text-decoration: none; color: inherit;");
		content.href =  url_list_Sessions + "?rich&no_menus&index&game=" + pkg; 
		content.innerHTML = sessions;
	} else {
		content = document.createTextNode(sessions);
	}   
	th.appendChild(content);

	th.colSpan = lb_cols - name_cols;
	th.className = 'leaderboard normal'
		th.style.textAlign = 'center';
	tr.appendChild(th);

	// Three optional rows only relevant for sessions
	if (session) {	
		// #############################################################
		// Second (optional) Header Row (session details if requested)
	
		if (details) {
			let tr = document.createElement('TR');
			tableHead.appendChild(tr);
	
			let td = document.createElement('TD');
			td.innerHTML = session.details_html;
			td.colSpan = lb_cols;
			td.className = 'leaderboard normal'
			tr.appendChild(td);
		
		// If no details are displayed at least show the date-time of the session
		// that produced this leaderboard snapshot
		} else {
			let tr = document.createElement('TR');
			tableHead.appendChild(tr);
	
			let th = document.createElement('TH');
	
			// content = document.createTextNode("Results after " + date_time);
	
			const intro = document.createTextNode("Results after ");
	
			if (session.link) {
				content = document.createElement('a');
				content.setAttribute("style", "text-decoration: none; color: inherit;");
				content.href = session.link;
				content.innerHTML = session.date_time;
			} else {
				content = document.createTextNode(session.date_time);
			}
	
			th.appendChild(intro);
			th.appendChild(content);
			th.colSpan = lb_cols;
			th.className = 'leaderboard normal'
			tr.appendChild(th);		
		}
	
		// #############################################################
		// Third Header Row (pre session analysis)
	
		if (analysis_pre) {
			let tr = document.createElement('TR');
			tableHead.appendChild(tr);
	
			let td = document.createElement('TD');
			td.innerHTML = session.analysis_pre_html;
			td.colSpan = lb_cols;
			td.className = 'leaderboard normal'
			tr.appendChild(td);
		}
	
		// #############################################################
		// Fourth Header Row (post session analysis)
	
		if (analysis_post) {
			let tr = document.createElement('TR');
			tableHead.appendChild(tr);
	
			let td = document.createElement('TD');
			td.innerHTML = session.analysis_post_html;
			td.colSpan = lb_cols;
			td.className = 'leaderboard normal'
			tr.appendChild(td);
		}
	}

	// #############################################################
	// Fifth Header Row (Player table header)

	tr = document.createElement('TR');
	tableHead.appendChild(tr);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Rank"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	if (show_d_rank && !hide_d_rank) {
		th = document.createElement('TH');
		th.style.textAlign = 'center';
		th.appendChild(document.createTextNode("Δ"));
		th.className = 'leaderboard normal'
		tr.appendChild(th);
	}

	th = document.createElement('TH');
	th.appendChild(document.createTextNode("Player"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	th = document.createElement('TH');
	th.style.textAlign = 'center';
	th.appendChild(document.createTextNode("Teeth"));
	th.className = 'leaderboard normal'
	tr.appendChild(th);

	if (show_d_rating && !hide_d_rating) {
		th = document.createElement('TH');
		th.style.textAlign = 'center';
		th.appendChild(document.createTextNode("Δ"));
		th.className = 'leaderboard normal'
		tr.appendChild(th);
	}

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
	// The Body (List of players)

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
		
		let td_class = 'leaderboard normal';
		
		const this_player = player_list[i][iPK]; 

		// Highlight the session players if we can (if it's a session snapshot)
		if (session) {
			// session.players is the list of players in the game session that
			// resulted in this leaderboard snapshot.
			if (session.players.indexOf(this_player) >= 0)
				td_class += highlight_players ? ' highlight_players_on' : ' highlight_players_off';
		} 

		// selected_players a list of players to highlight when highligh_selected is true
		if (selected_players && selected_players.includes(this_player.toString())) 
			td_class += highlight_selected ? ' highlight_selected_on' : ' highlight_selected_off'; 

		// Not a number by default
		let rank_delta = NaN; 
		let rating_delta = NaN; 

		// if a previous rank is available in the leaderboard 
		if (have_previous_ranks) {
			const rank       = player_list[i][iRank];
			const prev_rank  = player_list[i][iRankPrev];
			
			if (typeof prev_rank == 'number')  // Denotes a possible change in rank
				rank_delta = prev_rank - rank;
			else if (prev_rank == null)        // Denotes a new leaderboard entry
				rank_delta = null; 
			else							   // should never happen!
				rank_delta = NaN;
			
			if (rank_delta != 0)
				td_class += (highlight_changes && !hide_d_rank) ? ' highlight_changes_on' : ' highlight_changes_off';
		} 

		// if a previous rating is available in the leaderboard 
		if (have_previous_ratings) {
			const rating       = player_list[i][iEta];
			const prev_rating  = player_list[i][iRatingPrev];
			
			if (typeof prev_rating == 'number')  // Denotes a posisble change in rating
				rating_delta = rating - prev_rating;
			else if (prev_rating == null)    	 // Denotes a new leaderboard entry
				rating_delta = null; 
			else							     // should never happen!
				rating_delta = NaN;
			
			if (rating_delta !== 0)
				td_class += (highlight_changes && !hide_d_rating) ? ' highlight_changes_on' : ' highlight_changes_off';
		} 

		const pkp = player_list[i][iPK];
		const BGGname = player_list[i][iBGGname];
		const rating  = player_list[i][iEta];
		const mu  = player_list[i][iMu];
		const sigma  = player_list[i][iSigma];
		const plays  = player_list[i][iPlays];
		const wins  = player_list[i][iWins];
		const play_count  = player_list[i][iPlays];
		const victory_count  = player_list[i][iWins];
		
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
		// The Rank DELTA column
		if (show_d_rank && !hide_d_rank) {
			const td_rank_delta = document.createElement('TD');
			td_rank_delta.style.textAlign = 'center';
			td_rank_delta.className = td_class;
			
			content = rank_delta == 0 ? '-' 
				    : rank_delta == null ? '↥'
					: (rank_delta > 0 ? '↑' : '↓') + Math.abs(rank_delta);
			
			const div_rank_delta = document.createElement('div');
			div_rank_delta.setAttribute("class", "tooltip");
			div_rank_delta.innerHTML = content;
			
			const tt_rank_delta = document.createElement('span');
			
			const tt_text = rank_delta == 0 ? 'Rank unchanged' 
						  : rank_delta == null ? 'First entry on this leaderboard'
						  : 'Rank went ' 
							+ (rank_delta > 0 ? 'up ' : 'down ') 
							+ Math.abs(rank_delta) 
							+ (Math.abs(rank_delta) > 1 ? ' places' : ' place')
							+ ' from rank ' + (rank+rank_delta);
			
			tt_rank_delta.className = "tooltiptext";
			tt_rank_delta.style.width='15ch';
			tt_rank_delta.innerHTML = tt_text;
		
			div_rank_delta.appendChild(tt_rank_delta);
			td_rank_delta.appendChild(div_rank_delta);
			tr.appendChild(td_rank_delta);
		}

		// ###########################################################################
		// The PLAYER column
		const chosen_name = name_format == 'nick' ? player_list[i][iNickName]	
		                  : name_format == 'full' ? player_list[i][iFullName]
			        	  : name_format == 'complete' ? player_list[i][iCompleteName]
		                  : "ERROR";		
		
		const td_player = document.createElement('TD');
		td_player.className = td_class;
		
		if (linkPlayer) {
			const a_player = document.createElement('a');
			a_player.setAttribute("style", "text-decoration: none; color: inherit;");
			a_player.href =  linkPlayer; 
			a_player.innerText = chosen_name;
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
		tt_rating.style.width='12ch';
		tt_rating.innerHTML = "&mu;=" + fixed_mu + " &sigma;=" + fixed_sigma; 
		
		div_rating.appendChild(tt_rating);
		td_rating.appendChild(div_rating);
		tr.appendChild(td_rating);		

		// ###########################################################################
		// The Rating  DELTA column
		if (show_d_rating && !hide_d_rating) {
			const precision = 2
			const fixed_delta = typeof rating_delta == 'number' ? rating_delta.toFixed(precision) : rating_delta;
			
			const td_rating_delta = document.createElement('TD');
			td_rating_delta.style.textAlign = 'center';
			td_rating_delta.className = td_class;
			
			content = rating_delta == 0 ? '-' 
				    : rating_delta == null ? '↥'
					: (rating_delta > 0 ? '↑' : '↓') + Math.abs(fixed_delta);
			
			const div_rating_delta = document.createElement('div');
			div_rating_delta.setAttribute("class", "tooltip");
			div_rating_delta.innerHTML = content;
			
			const tt_rating_delta = document.createElement('span');
			
			const tt_text = rating_delta == 0 ? 'Rating unchanged' 
				    	  : rating_delta == null ? 'First entry on this leaderboard'
						  : 'Rating went ' 
							+ (rating_delta > 0 ? 'up ' : 'down ') 
							+ Math.abs(fixed_delta) 
							+ (Math.abs(rating_delta) > 1 ? ' teeth' : ' tooth')
							+ ' from ' + (rating-rating_delta).toFixed(precision)
							+ ' to ' + rating.toFixed(precision);
			
			tt_rating_delta.className = "tooltiptext";
			tt_rating_delta.style.width='15ch';
			tt_rating_delta.innerHTML = tt_text;
		
			div_rating_delta.appendChild(tt_rating_delta);
			td_rating_delta.appendChild(div_rating_delta);
			tr.appendChild(td_rating_delta);
		}
		
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

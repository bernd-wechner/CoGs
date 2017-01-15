SELECT 
  "Leaderboards_rating".game_id, 
  "Leaderboards_rating".plays, 
  "Leaderboards_rating".player_id, 
  "Leaderboards_player".name_nickname, 
  "Leaderboards_league_players".league_id
FROM 
  public."Leaderboards_rating", 
  public."Leaderboards_player", 
  public."Leaderboards_league_players"
WHERE 
  "Leaderboards_rating".player_id = "Leaderboards_player".id AND
  "Leaderboards_player".id = "Leaderboards_league_players".player_id AND
  "Leaderboards_rating".game_id = 31;

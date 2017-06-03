SELECT 
  "Leaderboards_game".id, 
  "Leaderboards_rating".id, 
  "Leaderboards_rating".game_id, 
  "Leaderboards_rating".player_id, 
  "Leaderboards_player".name_nickname, 
  "Leaderboards_game".name
FROM 
  public."Leaderboards_rating", 
  public."Leaderboards_player", 
  public."Leaderboards_game"
WHERE 
  "Leaderboards_rating".game_id = "Leaderboards_game".id AND
  "Leaderboards_rating".player_id = "Leaderboards_player".id AND
  "Leaderboards_game".id = 1 AND
  "Leaderboards_player".id =1;

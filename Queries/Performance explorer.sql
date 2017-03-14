SELECT 
  "Leaderboards_performance".id, 
  "Leaderboards_player".name_nickname, 
  "Leaderboards_player".name_personal, 
  "Leaderboards_player".name_family, 
  "Leaderboards_performance".play_number, 
  "Leaderboards_performance".victory_count, 
  "Leaderboards_performance".session_id, 
  "Game".name, 
  "Leaderboards_session".date_time
FROM 
  public."Leaderboards_performance"
  LEFT OUTER JOIN public."Leaderboards_player"
  ON "Leaderboards_performance".player_id = "Leaderboards_player".id
  LEFT OUTER JOIN public."Leaderboards_session"
  ON "Leaderboards_performance".session_id = "Leaderboards_session".id
  LEFT OUTER JOIN public."Leaderboards_game" "Game"
  ON "Leaderboards_session".game_id = "Game".id
WHERE 
  "Leaderboards_performance".session_id = 580;

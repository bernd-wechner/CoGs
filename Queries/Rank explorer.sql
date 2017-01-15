SELECT 
  "Leaderboards_rank".id, 
  "Leaderboards_rank".rank, 
  "Leaderboards_rank".session_id, 
  "Leaderboards_rank".player_id, 
  "Leaderboards_rank".team_id, 
  "Leaderboards_game".name, 
  "Leaderboards_session".date_time, 
  "Leaderboards_player".name_nickname, 
  "Leaderboards_player".name_personal, 
  "Leaderboards_player".name_family
FROM 
  public."Leaderboards_rank"
  LEFT OUTER JOIN public."Leaderboards_session"
  ON "Leaderboards_rank".session_id = "Leaderboards_session".id
  LEFT OUTER JOIN public."Leaderboards_game"
  ON "Leaderboards_session".game_id = "Leaderboards_game".id
  LEFT OUTER JOIN public."Leaderboards_player"
  ON "Leaderboards_rank".player_id = "Leaderboards_player".id
WHERE 
  "Leaderboards_rank".session_id = 537
ORDER BY
  "Leaderboards_rank".rank ASC;

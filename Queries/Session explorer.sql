SELECT 
  "Leaderboards_session".date_time, 
  "Leaderboards_game".name,
  "Leaderboards_rank".rank,
  "Leaderboards_performance".player_id
FROM 
  public."Leaderboards_session" 
  LEFT OUTER JOIN public."Leaderboards_rank" 
  ON "Leaderboards_rank".session_id = "Leaderboards_session".id
  LEFT OUTER JOIN public."Leaderboards_performance"
  ON "Leaderboards_performance".session_id = "Leaderboards_session".id
  LEFT OUTER JOIN public."Leaderboards_game"
  ON "Leaderboards_session".game_id = "Leaderboards_game".id
WHERE
   "Leaderboards_session".id = 580
ORDER BY "Leaderboards_rank".rank

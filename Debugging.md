Testing of new Form Code
Specifically:

1) Load add form with default (inherited) individual mode
    This seems to work. Although it would be nice if number of players was inherited too, if not the actual players.

2) Load add form with default (inherited) team mode
    Yet to test - have to save a team mode session first and then test inheritance and page initialisatioon

3) Swapping modes back and forth on a flexi game with saves between
    Seems to be working fine now


leaderboard filter refactor:

TODO:

Tidy up leaderboards page:

Want to implement a cache in the session.
Basically what the ajax_Leaderboards produce but we want to make player filtering possible on cached data.
And so on each player tuple we need enough info to do the filtering in ajax_Leaderboards on the cached
without a database fetch.

These they be:
player_filters = {'players',
                  'num_players_top',
                  'num_players_above',
                  'num_players_below',
                  'min_plays',
                  'played_since',
                  'player_leagues_any',
                  'player_leagues_all'}

And a player tuple currently holds:

(player.pk, player.BGGname, player.name, rating.trueskill_eta, rating.plays, rating.victories)

So we want to add last_play (datetime) and player_leagues (list of pks) to become:

(player.pk, player.BGGname, player.name, player.leagues, rating.trueskill_eta, rating.plays, rating.victories, rating.last_play)

In the Game model:

    last_performances
    session_list
    play_counts
    leaderboard

all take leagues and should support an any/all mode on that.

leaderboard in particular needs a mode or another method that doesn't filter on leagues, and adds all the info
the leaderboards view needs ...

TO FIX: When selecting a game in the session form, the new select2 control is great, but when the new game is selected we need to fetch the game info and update bounds of the num players box. Not happening. Entered Citadels and couldn't do more than 4 players.

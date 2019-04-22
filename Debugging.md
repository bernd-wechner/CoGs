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

1) Look into a placeholder value for the widgets when they are empty to contain ALL_LEAGUES, ALL_GAMES, ALL_PLAYERS as before.

2) Remove three buttons, one will do
Make these three radio buttons to choose a quick option perhaps and JS only selecting other options when clicked?
Teh strategy of JS clickers is good Through

3) Regroup Leagues, Games, Players

 Games can be top n games or a list.
 Players should include a list of players boards but a subsection on list compacting which offers
    only top n players on each boards
    only players who've played the game at least n times
    only players who've played the game since date/time
    +/-n each side of listed players (for focus)

'''
TrueSkill Helpers

Considerable analysis of TrueSkill is presented in "Understanding TrueSkill".

Some of the methods developed therein are provided here for use in analyses.

Some naming conventions used herein:

Symbols are generally treu to those used in "Understanding TrueSkill"

1) Greek symbols are spelled out by name
2) Roman symbols just use the appropriate letter
3) More difficult symbols are adhoc or described

Examples:

mu        The greek letter mu, representing the mean of a Normal (Gaussian) PDF (Probability Density Function)
sigma     The standard deviation of such a PDF
sigma2    The variance of such a PDF (being sigma**2 - i.e. the standard deviation squared)
tau       The greek letter tau, representing the TrueSkill Dynamic Factor (modelling rising uncertainty between plays)
beta      The greek letter beta, representing the TrueSkill SkillFactor (modelling the difference between performance and skill)
w         A partial play weighting
phi       The Normal (Gaussian) CDF
epsilon   The greek letter epsilon, representing the TrueSkill Draw Margin
p         (lower case p) The TrueSkill Draw Probability.
P         (upper case p) A general probability (of something)

Terms of use in reading this code:

skill            a mean and variance pair that models a players skill
rating           a single number derived from skill to rank players by
performance      a mean and variance pair that models the performance of player in a game
player           a single person who plays in a game
team             a group of players that cooperate/collude and share in their victory or otehr ranking as a unit
performer        a player or team
ranker           a performer when dealing with ranks (the ordered outcome of a game, predicted or observed)
'''

# Python imports
import trueskill

from collections import namedtuple
from math import sqrt, prod
from scipy.special import erf, erfinv
from scipy.stats import norm
from sortedcontainers import SortedDict

# Debug logging
from django.conf import settings
from Site.logutils import log


def phi(x):
    '''
    The Normal distribution CDF (Cumulative Distribution Function)

    '''
    return norm.cdf(x)  # alternately: return 0.5 * (1 + erf(x / sqrt(2))) # provides the same result.


# Skill in TrueSkill is modelled by a Normal (Gaussian) PDF with a mean and variance in a named tuple
# We store variance and not standard deviation in the tuple because that is more useful in many equations
# and permits consistency with Performance (next up)
Skill = namedtuple("Skill", ("mu", "sigma2"))

# Performance in TrueSkill is also modelled by a Normal (Gaussian) PDF. It captures the notion that
# for a given skill which a player posseses, their performance varies from day to day (because of
# other factors beyond their skill, the primary ones being described as "luck", and so beta
# is used to model the luck element in a game, and "absence" and so tau is used to model th eeffects
# of not playing since the last recorded session). See "Understanding TrueSkill" for a discusson on
# the shortcomings of this model (in particular tau is a fixed quantity in standard TrueSkill and not
# a function fo time, and both effects, arguably could/should impact the expected value too not just
# the variance.
Performance = namedtuple("Performance", ("mu", "sigma2", "w"))


class TrueSkillHelpers:
    '''
    A number of helpers to accompany the trueskill package. Technically could/should be in the trueskill package.

    They are based on the document "Understanding TrueSkill" (unpublished but should accompany this file really).

    The methods herein starting with P return probabilities (0-1). That is the focus of interest here. The trueskill
    package implements trueskill updates. BUt there are a string of probabilities that are of interest to anyone
    applying trueskill.

    Performance in this context is very different to the Performance object in the Leaderboards Django app that this
    file is part of. It represents the random variable that describes the performance of a player (or team) based on
    their skill and other variables.

    The other variables are in fact only two in trueskill, being:

    Tau, the Dynamics Factor, which describes essentially skill uncertainty that arises from absense from the game
    (this is very poorly modelled for tabletop games alas in trueskill as it's a constant between game factor and
    not dependent upon time in any way. There is a call to fix that here:

        https://github.com/bernd-wechner/CoGs/issues/13

    Beta, the Skill Factor, which describes essentially the role skill plays in the game (vs luck) and determines
    how far a skill's Mu will move in response to ne evidence (game results). Either way Beta figures prominently
    in probability calculations, generally adding to the uncertainty in skill. Seen another way, it is also a measure
    of how much we expecte performance to vary given a particular skill. And one argument is that it's luck that adds
    to variance. But it can equally well be describing the lundertainty due to any skill detracting features (luck,
    distracting background noise, interruptions, lack of sleep, hunger, lighting, whatever). it is hte prime
    contributor to performance variation over for a given skill rating. It can be tuned for a given game (the luck
    element differentiating games), but how is not queite clear. The issue is discussed here:

        https://github.com/bernd-wechner/CoGs/issues/21

    The key goals here for the Leaderboards app are:

    1) Predict a ranking given a set of player skills
    2) Describe the confidence we have in a given predicted ranking
    3) Describe the match quality (TODO) this is a measure of how enjoyable this match should have been
        (aka how

    '''
    tau = trueskill.TAU
    beta = trueskill.BETA
    p = trueskill.DRAW_PROBABILITY
    epsilon = None  # TrueSkill does not specify a default epsilon but it is ~0.74 for the default p. See self._epsilon()

    def __init__(self, tau=None, beta=None, p=None, epsilon=None):
        if tau: self.tau = tau
        if beta: self.beta = beta

        if epsilon and p:
            raise ValueError("Specify only one of epsilon and Pdraw!")

        if epsilon:
            self.epsilon = epsilon
            self.p = self._p()

        if p:
            self.epsilon = self._epsilon()
            self.p = p

    #####################################################################################################
    # # Internal helpers

    def _p(self):
        return erf(0.5 * self.epsilon / self.beta)

    def _epsilon(self):
        return 2 * self.beta * erfinv(self.p)

    #####################################################################################################
    # # Performance tuple constructors

    def performance(self, skill, ppw=None):
        '''
        Trueskill models a players skill with a normal distributon described by (mu, sigma).

        Performance during a game is differentiated from skill as it may vary. Good days, bad days and so on.

        See "Player Performance" in "Understanding TrueSkill"

        Specifically performance just has more variance, less certainty, but the same expectation as skill.

        :param skill: a Skill tuple
        :param ppw:    An optional, partial play weighting (defaults to 1)
        '''
        if not ppw: ppw = 1
        return Performance(skill.mu, skill.sigma2 + self.tau ** 2 + self.beta ** 2, ppw)

    def team_performance(self, performances):
        '''
        Trueskill models a teams performance as the weighted sum of individual player performances.

        Performance during a game is differentiated from skill as it may vary. Good days, bad days and so on.

        See "Team Performance" in "Understanding TrueSkill"

        Note: Individual players can be modelled as 1-player teams and this should yield the single players
        performance unchanged.

        :param performances: a list (or tuple) of Performance or Skill tuples.
        '''
        # For flexibility accept a single Performance if provided
        # This empowers a caller to loop over ranks and pass lists of performances (for ties or teams)
        # or Performance tuples for individuals (ranking alone or playing alone) without having to force
        # the singletons into lists (i.e. we do that here).
        if isinstance(performances, (Performance, Skill)):
            performances = [performances]

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance in enumerate(performances):
            if isinstance(performance, Skill):
                performances[i] = self.performance(performance)

        # Team performance is also returned in a Performance tuple, but the partial play weighting is irrelevant,
        # but is set to the sum of the individual partial play weights as measure of the team weight.
        return Performance(
                    sum([p.w * p.mu for p in performances]),
                    sum([p.w ** 2 * p.sigma2 for p in performances]),
                    sum([p.w for p in performances])
                )

    def mean_performance(self, performances):
        '''
        team performance is based upon the premise that team members are collaborating.

        If a number of competing performers have tied it can be useful to know the mean performance
        of all those tied performers. This is especially the case when looking at probabilities later.

        That is in P_win_2players below if performer A or B is a group of tied performers, their
        mean performance can be used to evaluate the win probability.

        Note: This is in fact the same as team_performance with a forced weighting of 1/n where n is
        number of performances.

        :param performances: a list (or tuple) of Performance or Skill tuples.
        '''
        # For flexibility accept a single Performance if provided
        # This empowers a caller to loop over ranks and pass lists of performances (for ties or teams)
        # or Performance tuples for individuals (ranking alone or playing alone) without having to force
        # the singletons into lists (i.e. we do that here).
        if isinstance(performances, (Performance, Skill)):
            performances = [performances]
        elif isinstance(performances, tuple):
            performances = list(performances)

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # The partial play weighting is irrelevant as we are about to force it to 1/n
        for i, performance in enumerate(performances):
            if isinstance(performance, Skill):
                performances[i] = self.performance(performance)

        # Force the partial play weighting to 1/n
        weight = 1 / len(performances)
        for i, p in enumerate(performances):
            performances[i] = Performance(p.mu, p.sigma2, weight)

        return self.team_performance(performances)

    #####################################################################################################
    # # Predictors

    def predicted_ranking(self, performances):
        '''
        Will return an ordered list of keys (or lists of keys), being the predicted
        ranking based on the expected performances (the mu of the Performance)

        :param performances: A dict with any key containing a Performance tuple
        '''
        # Allow for Skill tuples and just build default Performance tuples as needed.
        # Partial play weightings are meaningless for this prediction.
        for key, performance in performances.items():
            if isinstance(performance, Skill):
                performances[key] = self.performance(performance)

        # SortedDict does the work for us
        sorted_performances = SortedDict()

        for key, perf in performances.items():
            if not perf.mu in sorted_performances:
                sorted_performances[perf.mu] = key
            elif isinstance(sorted_performances[perf.mu], (list, tuple)):
                sorted_performances[perf.mu].append(key)
            else:
                sorted_performances[perf.mu] = [sorted_performances[perf.mu], key]

        # And return values sorted by the keys
        return sorted_performances.values()

    #####################################################################################################
    # # Win probability calculators

    def P_win_2players(self, performanceA, performanceB):
        '''
        Returns the probability that player A beats player B

        See "The Probability That One Player Beats Another" in "Understanding TrueSkill"

        We need performances not skills here, because Performance tuples include
        the influence of tau and beta. The partial play weighting is ignored and
        not relevant, but it is performance we need not skill.

        :param performanceA: a Performance or Skill tuple for player A
        :param performanceB: a Performance or Skill tuple for Player B
        '''
        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        if isinstance(performanceA, Skill):
            performanceA = self.performance(performanceA)
        if isinstance(performanceB, Skill):
            performanceB = self.performance(performanceB)

        # Build the performance delta
        delta = Performance(
                    performanceA.mu - performanceB.mu,
                    performanceA.sigma2 + performanceB.sigma2,
                    performanceA.w - performanceB.w  # Meaningless curio, not TrueSKill defined. But can convey the comparison of team weightings well!
            )

        return phi((delta.mu - self.epsilon) / sqrt(delta.sigma2))

    def P_win_2teams(self, performancesA, performancesB):
        '''
        The probability that team A beats team B.

        See "Team Performance" and "The Probability of a Draw Between Two Teams" in "Understanding TrueSkill"

        :param performancesA:    a list, tuple or set of Performance tuples for the players in team A
        :param performancesB:    a list, tuple or set of Performance tuples for the players in team B
        '''
        # For flexibility accept a single Performance if provided (for a team of 1 player)
        if isinstance(performancesA, (Performance, Skill)):
            performancesA = [performancesA]
        if isinstance(performancesB, (Performance, Skill)):
            performancesB = [performancesB]

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance in enumerate(performancesA):
            if isinstance(performance, Skill):
                performancesA[i] = self.performance(performance)

        for i, performance in enumerate(performancesB):
            if isinstance(performance, Skill):
                performancesB[i] = self.performance(performance)

        # Get the team performances
        performanceA = self.team_performance(performancesA)
        performanceB = self.team_performance(performancesB)

        # Build the performance delta
        delta = Performance(
                    performanceA.mu - performanceB.mu,
                    performanceA.sigma2 + performanceB.sigma2,
                    performanceA.w - performanceB.w  # Meaningless curio, not TrueSKill defined. But can convey the comparison of team weightings well!
            )

        # Assemble A's win probability
        return phi((delta.mu - self.epsilon) / sqrt(delta.sigma2))

    #####################################################################################################
    # # Draw probability calculators

    def P_draw_2players(self, performanceA, performanceB):
        '''
        The probability of a draw between two players

        See "The Probability of a Draw Between Two Players" in "understanding TrueSkill"

        We need performances not skills here, because Performance tuples include
        the influence of tau and beta. The partial play weighting is ignored and
        not relevant, but it is performance we need not skill.

        :param performanceA: a Performance or Skill tuple for player A
        :param performanceB: a Performance or Skill tuple for Player B
        '''
        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        if isinstance(performanceA, Skill):
            performanceA = self.performance(performanceA)
        if isinstance(performanceB, Skill):
            performanceB = self.performance(performanceB)

        # Build the performance delta
        delta = Performance(
                    performanceA.mu - performanceB.mu,
                    performanceA.sigma2 + performanceB.sigma2,
                    performanceA.w - performanceB.w  # Meaningless curio, not TrueSKill defined. But can convey the comparison of team weightings well!
            )

        return erf(self.epsilon / sqrt(2 * delta.sigma2))

    def P_draw_2teams(self, performancesA, performancesB):
        '''
        The probability of a draw between two teams.

        Teams use partial play weights.

        See "Team Performance" and "The Probability of a Draw Between Two Teams" in "Understanding TrueSkill"

        :param performancesA:    a list, tuple or set of Performance tuples for the players in team A
        :param performancesB:    a list, tuple or set of Performance tuples for the players in team B
        '''
        # For flexibility accept a single Performance if provided (for a team of 1 player)
        if isinstance(performancesA, (Performance, Skill)):
            performancesA = [performancesA]
        if isinstance(performancesB, (Performance, Skill)):
            performancesB = [performancesB]

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance in enumerate(performancesA):
            if isinstance(performance, Skill):
                performancesA[i] = self.performance(performance)

        for i, performance in enumerate(performancesB):
            if isinstance(performance, Skill):
                performancesB[i] = self.performance(performance)

        # Get the team performances
        performanceA = self.team_performance(performancesA)
        performanceB = self.team_performance(performancesB)

        # Build the performance delta
        delta = Performance(
                    performanceA.mu - performanceB.mu,
                    performanceA.sigma2 + performanceB.sigma2,
                    performanceA.w - performanceB.w  # Meaningless curio, not TrueSKill defined. But can convey the comparison of team weightings well!
            )

        return erf(self.epsilon / sqrt(2 * delta.sigma2))

    #####################################################################################################
    # # Ranking probability calculators

    def P_ranking_players(self, performances):
        '''
        The probability of a given ranking of players.

        See "The Probability of a Given Ranking" in "Understanding TrueSkill"

        We need performances not skills here, because Performance tuples include
        the influence of tau and beta. The partial play weighting is ignored and
        not relevant, but it is performance we need not skill.

        Note: This does not support ties! To wit is primarily conceptual and not very
        useful in practice.

        It should yield exactly the same result as P_ranking_teams with 1 player teams.

        :param performances: An ordered list (or tuple) of performances (mu/sigma2 pairs).
                             Ordered by rank (so 0 won, 1 came second, etc.)
                             e.g. [(mu1, sigma21), (mu2, sigma22), (mu3, sigma23), (mu4, sigma24)]
                             The partial Play Weighting (w) is ignored here (it is used in P_ranking_teams)

        '''
        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance in enumerate(performances):
            if isinstance(performance, Skill):
                performances[i] = self.performance(performance)

        P = [self.P_win_2players(performances[i], performances[i + 1]) for i in range(len(performances) - 1)]

        if len(P) == 0:
            prob = 1
        else:
            prob = prod(P)

        if settings.DEBUG:
            log.debug(f"Pwins={P}")
            log.debug(f"Pwins={prob}")

        return prob

    def P_ranking_teams(self, performances):
        '''
        The probability of a given ranking of teams.

        Note: This does not support ties! To wit is primarily conceptual and not very
        useful in practice.

        See "The Probability of a Given Ranking" in "Understanding TrueSkill"

        :param performances: An ordered list (or tuple) of lists (or tuples) of performances (mu/sigma/w triplets).
                             Ordered by rank (so 0 won, 1 came second, etc.)
                             e.g. ([(mu1, sigma21, w1), (mu2, sigma22, w2)], [(mu3, sigma23, w3)], [(mu4, sigma24, w4)])
        '''
        # For flexibility accept a single Performance if provided (for a team of 1 player)
        # This empowers a caller to loop over ranks and pass lists of performances (for ties or teams)
        # or Performance tuples for individuals (ranking alone or playing alone) without having to force
        # the singletons into lists (i.e. we do that here).
        for i, performance in enumerate(performances):
            if isinstance(performance, (Performance, Skill)):
                performances[i] = [performance]

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance_list in enumerate(performances):  # For each team
            for j, performance in enumerate(performance_list):  # For each player in the team
                if isinstance(performance, Skill):
                    performances[i][j] = self.performance(performance)

        P = [self.P_win_2teams(performances[i], performances[i + 1]) for i in range(len(performances) - 1)]

        return prod(P)

    def P_ranking_performers(self, performances):
        '''
        The probability of a given ranking of performers.

        This generalises P_ranking_players and P_ranking_teams supporting ties. Each entry in the supplied list
        is a single peerformer or list/tuple of tied performers. These can be player performances or team performances
        we make no assesment nor do we care here. This generalises well, and they should simply all be player
        performances or team performances depending upon the style of game being played.

        See "The Probability of a Given Ranking" in "Understanding TrueSkill"

        :param performances: An ordered list (or tuple) of performances or lists (or tuples) of performances (mu/sigma/w triplets).
                             Ordered by rank (so 0 won, 1 came second, etc.)
                             A single performance represents a player or team performance (no assessment is made herein the caller takes responsibiltiy)
                             A list represents tied performers (which could be player or team performances again, callers responsibility).
                             e.g. ([(mu1, sigma21, w1), (mu2, sigma22, w2)], [(mu3, sigma23, w3)], [(mu4, sigma24, w4)])
        '''

        # Collect the performances at each rank
        # For ties we take the mean of all the tied performers
        ranked_performances = []
        for performance in performances:
            if isinstance(performance, Performance):
                ranked_performances.append(performance)
            elif isinstance(performance, (list, tuple)):
                ranked_performances.append(self.mean_performance(performance))
            else:
                raise ValueError("Illegal entry in performances (must be Performance or list/tuple")

        # Collect the 2 performer win win probabilities, ie. Probability A beats B for 1/2, 2/3, 3/4 etc.
        Pwins = self.P_ranking_players(ranked_performances)

        # Collect the draw probabilities for each tied performance
        Pdraws = []
        for performance in performances:
            if not isinstance(performance, (Performance, Skill)) and isinstance(performance, (list, tuple)):
                for i in range(len(performance) - 1):
                    Pdraws.append(self.P_draw_2players(performance[i], performance[i + 1]))

        if settings.DEBUG:
            log.debug(f"{Pdraws=}")

        if Pdraws:
            Pdraws = prod(Pdraws)
        else:
            Pdraws = 1

        if settings.DEBUG:
            log.debug(f"{Pdraws=}")

        return Pwins * Pdraws

    #####################################################################################################
    # # Leaderboard app interfaces

    def Update_skills(self, session):
        pass

    def Predicted_ranking(self, session, with_performances=False, after=False):
        '''
        Returns a tuple of players or teams that represents the preducted ranking given their skills
        before (or after) the nominated session and a probability of that ranking in a 2-tuple.

        Each list item can be:

        A player (instance of the Leaderboard app's Player model)
        A team (instance of the Leaderboard app's Team model)
        A list of either players or teams - if a tie is predicted at that rank

        :param session: an instance of the leaderboards model Session
        :param with_performances: if Ture includes a tuple of expected performances mapping one to one mapping with the tuple of players/teams
        :param after: if true, gets and uses skills "after" rather than "before" the present ranks (recorded play session).
        '''

        # For predicted rankings we assume a partial play weighting of 1 (full participation)
        # The recorded partial play waighting has no impact on what ranking we would predict for
        # these performers, before or after the sessions skill updates.
        def P(player, after):
            p = session.performance(player)
            return Performance(
                            p.trueskill_mu_after if after else p.trueskill_mu_before,
                            p.trueskill_sigma_after ** 2 if after else p.trueskill_sigma_before ** 2,
                            1
                        )

        # One dict to hold the performers and another to hold the performances
        performers = SortedDict(lambda perf: -perf)  # Keyed and sorted on trueskill_mu of the performer
        performances = SortedDict(lambda perf: -perf)  # Keyed and sorted on trueskill_mu of the performer

        if session.team_play:
            for team in session.teams:
                p = self.team_performance([P(player, after) for player in team.players.all()])
                k = p.mu

                if not k in performers:
                    performers[k] = []
                performers[k].append(team)

                if not p.mu in performances:
                    performances[k] = []
                performances[k].append(p)
        else:
            for player in session.players:
                p = P(player, after)
                k = p.mu

                if not k in performers:
                    performers[k] = []
                performers[k].append(player)

                if not k in performances:
                    performances[k] = []
                performances[k].append(p)

        # Freeze and flatten
        for k, tied_performers in performers.items():
            if len(tied_performers) == 1:
                performers[k] = tied_performers[0]  # Remove the list
            else:
                performers[k] = tuple(tied_performers)  # Freeze the list

        for k, tied_performances in performances.items():
            if len(tied_performances) == 1:
                performances[k] = tied_performances[0]  # Remove the list
            else:
                performances[k] = tuple(tied_performances)  # Freeze the list

        if settings.DEBUG:
            log.debug(f"\nPredicted_ranking:")
            for k in performers:
                log.debug(f"\t{performers[k]}: {performances[k]}")

        # Get the probability of this ranking
        prob = self.P_ranking_performers(tuple(performances.values()))

        # Return the ordered tuple
        if with_performances:
            return (tuple(performers.values()), prob, tuple(performers.keys()))
        else:
            return (tuple(performers.values()), prob)

    def Rank_performance(self, rank, after=False):
        '''
        A Rank can describe a single player or a team. Returns the appropriate TrueSkill performance
        using the helpers herein.

        We need to prepare a single performance tuple (mu sigma2, w) to return describing
        the TrueSkill performance of the player or team (of 1 maybe) that ranked here.

        :param rank: an instance of the leaderboards model Rank
        :param after: if true, gets and uses skills "after" rather than "before" the present ranks (recorded play session).
                      The ranks submitted influenced player skill ratings, so there's
                      a before-start context (the probability of this ranking given the skill ratings before play, and
                      an after-end context (the probability of this ranking given the skill ratings after  play).
        '''
        if rank.session.team_play:
            # Get the performances of the team players
            ps = [rank.session.performance(player) for player in rank.team.players.all()]

            # Convert this to a list of TrueSkill Performance tuples
            Ps = [Performance(
                            p.trueskill_mu_after if after else p.trueskill_mu_before,
                            p.trueskill_sigma_after ** 2 if after else p.trueskill_sigma_before ** 2,
                            p.partial_play_weighting
                        ) for p in ps]

            #  return the team performance
            return self.team_performance(Ps)
        else:
            # Get the Leaderboards Performance object associated with this rank
            p = rank.session.performance(rank.player)

            # Return  TrueSkill Performance tuple
            return Performance(
                            p.trueskill_mu_after if after else p.trueskill_mu_before,
                            p.trueskill_sigma_after ** 2 if after else p.trueskill_sigma_before ** 2,
                            p.partial_play_weighting
                        )

    def Actual_ranking(self, session, as_ranks=False, after=False):
        '''
        Like Predicted_ranking but returns the Actual ranking as a tuple of rankers and
        the probability of a recorded ranking (before or after the ranking was used to
        adjust player skills), using Leaderboards app Rank objects in an ordered list or
        tuple.

        We need to build a list ranked performance lists (mu, sigma2, w triplets) to pass
        to the internal helpers.

        These are derived from Django ORM Rank objects, imported in the header.

        For conformance with Predicted_ranking, a tuple of rankers (player or Team objects)
        is returned by default. But there is possible scoring information attached to the
        Rank objects which provide these rankers, and if a caller wishes to dislay rankers
        and scores they may wish to receive Rank objects which provides both.

        Predicted_ranking does not need this option as the prediction is based soley upon
        player ratings and scores are not predicted, only a ranking is.

        :param session: an instance of the leaderboards model Session
        :param as_ranks: If true, for each ranker their Rank object is returned else the ranker object is (Player or Team)
        :param after: if true, gets and uses skills "after" rather than "before" the present ranks (recorded play session).
                      The ranks submitted influenced player skill ratings, so there's
                      a before-start context (the probability of this ranking given the skill ratings before play, and
                      an after-end context (the probability of this ranking given the skill ratings after  play).
                      The comparison is interesting because the very aim of TrueSkill's skill adjustments is that the
                      probability of this ranking is higher with the updated skills. In short we should see TrueSkill
                      doing it's work if P_ranking(after) is higher than P_ranking(after) for a given set of ranks,
        '''

        # One dict to hold the rankers
        rankers = SortedDict()  # Keyed and sorted on trueskill_mu of the ranker
        # And another to hold the TrueSkill performances (i.e not Performance objects, but (mu, sigma, w) tuples)
        performances = SortedDict()  # Keyed and sorted on trueskill_mu of the ranker

        # Ordered by rank.rank by default
        for rank in session.ranks.all():
            if not rank.rank in rankers:
                rankers[rank.rank] = []
            rankers[rank.rank].append(rank if as_ranks else rank.ranker)

            if not rank.rank in performances:
                performances[rank.rank] = []
            performances[rank.rank].append(self.Rank_performance(rank, after))

        # Freeze and flatten
        for rank, tied_performers in rankers.items():
            if len(tied_performers) == 1:
                rankers[rank] = tied_performers[0]  # Remove the list
            else:
                rankers[rank] = tuple(tied_performers)  # Freeze the list

        for rank, tied_performances in performances.items():
            if len(tied_performances) == 1:
                performances[rank] = tied_performances[0]  # Remove the list
            else:
                performances[rank] = tuple(tied_performances)  # Freeze the list

        prob = self.P_ranking_performers(tuple(performances.values()))

        # Return the ranking probability of those performances
        return (tuple(rankers.values()), prob)


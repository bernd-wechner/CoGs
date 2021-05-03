'''
TrueSkill Helpers

Considerable analysis fo TrueSkill is presented in "Understanding TrueSkill.

Some of the methods developed therein are provided here for use in analyses.

Some naming conventions used herein:

Symbols are generally treu to those used in "Understanding TrueSkill"

1) Greek symbols are spelled out by name
2)  Roman symbols just use the appropriate letter
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
'''

# Python imports
import trueskill

from collections import namedtuple
from math import sqrt, prod
from scipy.special import erf, erfinv
from scipy.stats import norm

# Debug logging
from django.conf import settings
from CoGs.logging import log


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

        :param performances: a list (or tuple) of Performance tuples.
        '''
        # For flexibility accept a single Performance if provided
        # This empowers a caller to loop over ranks and pass lists of performances (for ties or teams)
        # or Performance tuples for individuals (ranking alone or playing alone) without having to force
        # the singletons into lists (i.e. we do that here).
        if isinstance(performances, Performance) or isinstance(performances, Skill):
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

        return phi((performanceA.mu - performanceA.mu - self.epsilon) / sqrt(performanceA.sigma2 + performanceA.sigma2))

    def P_win_2teams(self, performancesA, performancesB):
        '''
        The probability that team A beats team B.

        See "Team Performance" and "The Probability of a Draw Between Two Teams" in "Understanding TrueSkill"

        :param performancesA:    a list, tuple or set of Performance tuples for the players in team A
        :param performancesB:    a list, tuple or set of Performance tuples for the players in team B
        '''
        # For flexibility accept a single Performance if provided (for a team of 1 player)
        if isinstance(performancesA, Performance) or isinstance(performancesA, Skill):
            performancesA = [performancesA]
        if isinstance(performancesB, Performance) or isinstance(performancesB, Skill):
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

        return erf(self.epsilon / sqrt(2 * (performanceA.sigma2 + performanceB.sigma2)))

    def P_draw_2teams(self, performancesA, performancesB):
        '''
        The probability of a draw between two teams.

        Teams use partial play weights.

        See "Team Performance" and "The Probability of a Draw Between Two Teams" in "Understanding TrueSkill"

        :param performancesA:    a list, tuple or set of Performance tuples for the players in team A
        :param performancesB:    a list, tuple or set of Performance tuples for the players in team B
        '''
        # For flexibility accept a single Performance if provided (for a team of 1 player)
        if isinstance(performancesA, Performance) or isinstance(performancesA, Skill):
            performancesA = [performancesA]
        if isinstance(performancesB, Performance) or isinstance(performancesB, Skill):
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
        But P_ranking_teams can be used to model ties (a team being a group of tied people).

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

        P = [phi((performances[i].mu - performances[i + 1].mu - self.epsilon) / sqrt(performances[i].sigma2 + performances[i + 1].sigma2)) for i in range(len(performances) - 1)]

        return prod(P)

    def P_ranking_teams(self, performances):
        '''
        The probability of a given ranking of teams.

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
            if isinstance(performance, Performance) or isinstance(performance, Skill):
                performances[i] = [performance]

        # Allow for Skill tuples and just build default Performance tuples as needed.
        # This would capture the default partial play weighting of 1. The caller must
        # supply Performance tuples to specify different partial play weightings.
        for i, performance_list in enumerate(performances):
            for j, performance in enumerate(performance_list):
                if isinstance(performance, Skill):
                    performances[i][j] = self.performance(performance)

        # Collect the team performances
        team_performances = []
        for performance_list in performances:
            team_performances.append(self.team_performance(performance_list))

        P = [phi((team_performances[i].mu - team_performances[i + 1].mu - self.epsilon) / sqrt(team_performances[i].sigma2 + team_performances[i + 1].sigma2)) for i in range(len(team_performances) - 1)]

        return prod(P)

    #####################################################################################################
    # # Leaderboard app interfaces

    def Rank_performance(self, ranks, after=False):
        '''
        A Rank can describe a single player or a team. Returns the approriate TrueSkill performance
        using the helpers herein.

        We need to prepare a single perfomance tuple (mu sigma2, w) to return describing
        the TrueSkill performance of the team (of 1 maybe) that ranked here.

        A note on ties: the Rank model captures the player or team and its rank in the game result.
        In case of ties more than one Rank objecthas the same ranking. These can/should present here
        as a list (or tuple or set) of Rank objects.

        There are two contexts of use:

        1) Calculating the probability of a ranking (P_ranking below), in which case we want a team
            performance for everyone in every team that ranked at this spot. A list (or tuple or set)
            of Rank objects that includes all Ranks tied at this ranking can be passed in for that.

        2) Reporting the TrueSkill performance of a given ranker (player or team), in which case we
            want a team performance for only that player or team (not all the tied ones) and a single
            Rank object can be passed in.

        :param ranks: an instance or list (or tupe or set) of instances of the leaderboards model Rank
        '''
        # If a single Rank is porvided force a list
        if not (isinstance(ranks, list) or isinstance(ranks, tuple) or isinstance(ranks, set)):
            ranks = [ranks]

        # Build a list of players who tied at this ranking
        # A list of 1 player is fine for no ties and not teams.
        players = []
        for rank in ranks:
            if rank.session.team_play:
                players.extend(list(rank.team.players.all()))
            else:
                players.append(rank.player)

        # Build a list of Leaderboards Performance objects related to each player
        Performances = [rank.session.performance(player) for player in players]

        # Build a list of TrueSkill Performance tuples related to each player
        performances = [Performance(
                            p.trueskill_mu_after if after else p.trueskill_mu_before,
                            p.trueskill_sigma_after ** 2 if after else p.trueskill_sigma_before ** 2,
                            p.partial_play_weighting
                        ) for p in Performances]

        # Assemble the team performance (team of 1 if individual player)
        return self.team_performance(performances)

    def P_ranking(self, ranks, after=False):
        '''
        The probability of a given ranking (before or afgter the ranking was used to adjust player skills),
        using Leaderboards app Rank objects in an ordered list or tuple.

        We need to build a list ranked performance lists (mu, sigma2, w triplets) to pass to the internal helpers.

        These are derived from Django ORM Rank objects, imported in the header.

        :param ranks: an list or tuple of sets, lists or tuples of Rank instances
                      i.e. each entry in the list or tuple has to be a set of player ranks
                      so either a team or a set of tied players or teams depending on context.
        :param after: if true, gets and uses skills "after" rather than "before" the present ranks (recorded play session).
                      The ranks submitted influenced player skill ratings, so there's
                      a before-start context (the probability of this ranking given the skill ratings before play, and
                      an after-end context (the probability of this ranking given the skill ratings after  play).
                      The comparison is interesting because the very aim of TrueSkill's skill adjustments is that the
                      probability of this ranking is higher with the updated skills. In short we should see TrueSkill
                      doing it's work if P_ranking(after) is higher than P_ranking(after) for a given set of ranks,
        '''
        # Permit singletons, that is the elemnts of ranks could be a single rank or a list/tuple of ranks (tied players or teams).
        for i, rank in enumerate(ranks):
            if not (isinstance(rank, list) or isinstance(rank, tuple) or isinstance(rank, set)):
                ranks[i] = [rank]

        # Each item in ranks is itself a list (of tied rankers) which may contain one item, or more
        performances = []
        for tied_ranks in ranks:
            # At each ranking we collect a whole group performance at that ranking (ties and teams all merged)
            performances.append(self.Rank_performance(tied_ranks, after))

        # We use P_ranking_teams as it supports 1 player teams.
        # Whereas P_ranking_players does not support teams (and is useless to us as a consequence).
        return self.P_ranking_teams(performances)


import trueskill

from django.db import models

class TrueskillSettings(models.Model):
    '''
    The site wide TrueSkill settings to use (i.e. not Game).
    '''
    # Changing these affects the entire ratings history. That is we change one of these settings, either:
    #    a) All the ratings history needs to be recalculated to get a consistent ratings result based on the new settings
    #    b) We keep the ratings history with the old values and move forward with the new
    # Merits? Methods?
    # Suggest we have a form for editing these with processing logic and don't let the admin site edit them, or create logic
    # that can adapt to admin site edits - flagging the likelihood. Or perhaps we should make this not a one tuple table
    # but store each version with a date. That in can of course then support staged ratings histories, so not a bad idea.
    mu0 = models.FloatField('TrueSkill Initial Mean (µ0)', default=trueskill.MU)
    sigma0 = models.FloatField('TrueSkill Initial Standard Deviation (σ0)', default=trueskill.SIGMA)
    delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)

    add_related = None

    def __unicode__(self): return u'µ0={} σ0={} δ={}'.format(self.mu0, self.sigma0, self.delta)

    def __str__(self): return self.__unicode__()

    class Meta:
        verbose_name = "Trueskill settings"
        verbose_name_plural = "Trueskill settings"

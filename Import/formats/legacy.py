'''
Game record importers

At present simply captures a couple of legacy importers used manually to import CSV data files.
'''

import csv
import pytz
from dateutil import parser
from datetime import datetime
from django.http import HttpResponse
from django.db import transaction
from django_rich_views.html import fmt_str

from Site.logutils import log
from .models import Team, Player, Game, League, Location, Session, Rank, Performance, Rating


def import_CoGs_sessions(request):
    title = "Import CoGs scoresheet"

    result = ""
    sessions = []
    with open('/home/bernd/workspace/CoGs/Seed Data/CoGs Scoresheet - Session Log.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            date_time = parser.parse(row["Date"])
            game = row["Game"].strip()
            ranks = {
                row["1st place"].strip(): 1,
                row["2nd place"].strip(): 2,
                row["3rd place"].strip(): 3,
                row["4th place"].strip(): 4,
                row["5th place"].strip(): 5,
                row["6th place"].strip(): 6,
                row["7th place"].strip(): 7
                }

            tie_ranks = {}
            for r in ranks:
                if ',' in r:
                    rank = ranks[r]
                    players = r.split(',')
                    for p in players:
                        tie_ranks[p.strip()] = rank
                else:
                    tie_ranks[r] = ranks[r]

            session = (date_time, game, tie_ranks)
            sessions.append(session)

    # Make sure a Game and Player object exists for each game and player
    missing_players = []
    missing_games = []
    for s in sessions:
        g = s[1]
        try:
            Game.objects.get(name=g)
        except Game.DoesNotExist:
            if g and not g in missing_games:
                missing_games.append(g)
        except Game.MultipleObjectsReturned:
            result += "{} exists more than once\n".format(g)

        for p in s[2]:
            try:
                Player.objects.get(name_nickname=p)
            except Player.DoesNotExist:
                if p and not p in missing_players:
                    missing_players.append(p)
            except Player.MultipleObjectsReturned:
                result += "{} exists more than once\n".format(p)

    if len(missing_games) == 0 and len(missing_players) == 0:
        result += fmt_str(sessions)

        Session.objects.all().delete()
        Rank.objects.all().delete()
        Performance.objects.all().delete()
        Rating.objects.all().delete()
        Team.objects.all().delete()

        for s in sessions:
            session = Session()
            session.date_time = s[0]
            session.game = Game.objects.get(name=s[1])
            session.league = League.objects.get(name='Hobart')
            session.location = Location.objects.get(name='The Big Blue House')
            session.save()

            for p in s[2]:
                if p:
                    rank = Rank()
                    rank.session = session
                    rank.rank = s[2][p]
                    rank.player = Player.objects.get(name_nickname=p)
                    rank.save()

                    performance = Performance()
                    performance.session = session
                    performance.player = rank.player
                    performance.save()

            Rating.update(session)
    else:
        result += "Missing Games:\n{}\n".format(fmt_str(missing_games))
        result += "Missing Players:\n{}\n".format(fmt_str(missing_players))

    return HttpResponse(f"<html><body<p>{title}</p><p>It is now {datetime.now()}.</p><p><pre>{result}</pre></p></body></html>")

def import_Wollongong_sessions(request):
    title = "Import Wollongong scoresheet"

    tz = pytz.timezone("Australia/Sydney")
    league_name = "Wollongong"

    result = ""
    sessions = []
    with open('/home/bernd/workspace/CoGs/Seed Data/Wollongong/Wollongong Game Records.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            game = row["Game"].strip()
            date_time = tz.localize(parser.parse(f"{row['Date']} {row['Time']}"))
            location = row["Location"]

            player_ranks = {}
            for player in ["René", "Dave H", "Darren", "Jason", "Amelia", "Stu"]:
                player_ranks[player] = row[player].strip()

            ranked_players = []
            for p in player_ranks:
                ranked_players.append("")

            for p in player_ranks:
                if player_ranks[p]:
                    try:
                        rank = int(player_ranks[p])
                    except:
                        rank = 0

                    if rank:
                        # Allowing for the possibility of ties (more than one player at same rank)
                        r = rank - 1
                        if ranked_players[r]:
                            ranked_players[r] += f",{p}"
                        else:
                            ranked_players[r] += p

            # TODO: ranked players must have consecutive ranks, i.e. all empty cells
            # at top or far right,

            session = (date_time, location, game, ranked_players)
            sessions.append(session)

    # Make sure a Game and Player object exists for each game and player
    missing_players = []
    missing_games = []
    missing_locations = []
    for s in sessions:
        date_time, location, game, ranked_players = s
        log.debug(f"Processing session: {s}")

        g = game
        try:
            Game.objects.get(name=g)
        except Game.DoesNotExist:
            if g and not g in missing_games:
                missing_games.append(g)
        except Game.MultipleObjectsReturned:
            result += "Game: {} exists more than once\n".format(g)

        l = location
        try:
            Location.objects.get(name=l)
        except Location.DoesNotExist:
            if l and not l in missing_locations:
                missing_locations.append(l)
        except Location.MultipleObjectsReturned:
            result += "Location: {} exists more than once\n".format(g)

        for Ps in ranked_players:
            for p in Ps.split(","):
                try:
                    Player.objects.get(name_nickname=p)
                except Player.DoesNotExist:
                    if p and not p in missing_players:
                        missing_players.append(p)
                except Player.MultipleObjectsReturned:
                    result += "Player: {} exists more than once\n".format(p)

    if len(missing_games) == 0 and len(missing_locations) == 0 and len(missing_players) == 0:
        existing_sessions = []
        for s in sessions:
            # First check if that session was already imported!
            date_time, location, game, ranked_players = s
            test = Session.objects.filter(date_time=date_time, location__name=location, game__name=game)

            if len(test):
                existing_sessions.append(s)
            else:
                try:
                    with transaction.atomic():
                        session = Session()
                        session.date_time = date_time
                        session.location = Location.objects.get(name=location)
                        session.game = Game.objects.get(name=game)
                        session.league = League.objects.get(name=league_name)
                        session.save()

                        for r, Ps in enumerate(ranked_players, 1):
                            # No support for teams here, we'll build a rank object and performance object for each player
                            for p in Ps.split(","):
                                if p:
                                    rank = Rank()
                                    rank.session = session
                                    rank.rank = r
                                    rank.player = Player.objects.get(name_nickname=p)
                                    rank.save()

                                    performance = Performance()
                                    performance.session = session
                                    performance.player = rank.player
                                    performance.save()

                        Rating.update(session)
                except Exception as E:
                    result += f"<p>Error: {E}<br>While processing session: {s}</p>"
                    transaction.rollback()

        if existing_sessions:
            result += "<p>These sessions not imported (already in system):<ul>"
            for s in existing_sessions:
                result += f"<li>{s}</li>"
            result += "</ul></p>"
    else:
        result += "Missing Games:\n{}\n".format(fmt_str(missing_games))
        result += "Missing Players:\n{}\n".format(fmt_str(missing_players))

    return HttpResponse(f"<html><body<p>{title}</p><p>It is now {datetime.now()}.</p><p><pre>{result}</pre></p></body></html>")

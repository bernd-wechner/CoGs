# Simple outline of an approach to fetching game data from BGG

import requests
import xmltodict


class BGG(dict):
    '''
    A simple class for fetching BGG data about a game
    '''
    __API_URL__ = 'https://www.boardgamegeek.com/xmlapi/boardgame/{id}'

    def __init__(self, game_id):
        URL = self.__API_URL__.format(id=game_id)
        response = requests.get(URL)
        data = xmltodict.parse(response.content)
        self.update(data['boardgames']['boardgame'])

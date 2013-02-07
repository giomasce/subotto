#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import datetime 
import os
from select import select
now=datetime.datetime.now

from data import Session, Team, Player, Match, PlayerMatch, Event, Base, AdvantagePhase

class SubottoCore:

    def __init__(self, match_id):
        self.session = Session()
        self.match = self.session.query(Match).filter(Match.id == match_id).one()
        self.teams = [self.match.team_a, self.match.team_b]
        self.order = [None, None]
        self.score = [0, 0]
        self.players = [[None, None], [None, None]]
        self.listeners = []

        self.last_event_id = 0
        self.last_player_match_id = 0
        self.last_timestamp = None

    def detect_team(self, team):
        if team == self.match.team_a:
            return 0
        else:
            return 1

    def new_player_match(self, player_match):
        print >> sys.stderr, "> Received new player match: %r" % (player_match)

        for listener in self.listeners:
            listener.new_player_match(player_match)

    def new_event(self, event):
        print >> sys.stderr, "> Received new event: %r" % (event)

        if event.type == Event.EV_TYPE_SWAP:
            self.order = [event.red_team, event.blue_team]

        elif event.type == Event.EV_TYPE_CHANGE:
            self.players[self.detect_team(event.team)] = [event.player_a, event.player_b]

        elif event.type == Event.EV_TYPE_GOAL:
            self.score[self.detect_team(event.team)] += 1

        elif event.type == Event.EV_TYPE_GOAL_UNDO:
            self.score[self.detect_team(event.team)] -= 1

        elif event.type == Event.EV_TYPE_ADVANTAGE_PHASE:
            pass

        else:
            print >> sys.stderr, "> Wrong event type %r\n" % (event.type)

        for listener in self.listeners:
            listener.new_event(event)

    def regenerate(self):
        print >> sys.stderr, "> Regeneration"
        for listener in self.listeners:
            listener.regenerate()

    def update(self):
        self.session.rollback()
        for player_match in self.session.query(PlayerMatch).filter(PlayerMatch.match == self.match).filter(PlayerMatch.id > self.last_player_match_id).order_by(PlayerMatch.id):
            self.new_player_match(player_match)
            self.last_player_match_id = player_match.id
        for event in self.session.query(Event).filter(Event.match == self.match).filter(Event.id > self.last_event_id).order_by(Event.id):
            if self.last_timestamp is not None and event.timestamp <= self.last_timestamp:
                print >> sys.stderr, "> Timestamp monotonicity error at %s!\n" % (event.timestamp)
                #sys.exit(1)
            self.new_event(event)
            self.last_timestamp = event.timestamp
            self.last_event_id = event.id
        self.regenerate()
        return True

    def act_event(self, event, source=None):
        event.timestamp = now()
        event.match = self.match
        if source is None:
            event.source = Event.EV_SOURCE_MANUAL
        else:
            event.source = source
        if not event.check_type():
            print >> sys.stderr, "> Sending bad event..."
        self.session.add(event)
        self.session.commit()
        self.update()

    def act_switch_teams(self, source=None):
        e = Event()
        e.type = Event.EV_TYPE_SWAP
        if self.order == [None, None]:
            e.red_team = self.teams[0]
            e.blue_team = self.teams[1]
        else:
            e.red_team = self.order[1]
            e.blue_team = self.order[0]
        self.act_event(e, source)

    def act_goal(self, team, source=None):
        e = Event()
        e.type = Event.EV_TYPE_GOAL
        e.team = team
        self.act_event(e, source)

    def act_goal_undo(self, team, source=None):
        e = Event()
        e.type = Event.EV_TYPE_GOAL_UNDO
        e.team = team
        self.act_event(e, source)

    def act_team_change(self, team, player_a, player_b, source=None):
        e = Event()
        e.type = Event.EV_TYPE_CHANGE
        e.team = team
        e.player_a = player_a
        e.player_b = player_b
        self.act_event(e, source)
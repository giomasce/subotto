#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import sys
import socket
import SocketServer
import time
import threading
import struct
import select
import argparse

from core import SubottoCore

running = True
dry_run = False

# Always hold this lock to access the core
core_lock = threading.Lock()
core = None

CODE_NOOP = 0
CODE_CELL_RED_PLAIN = 1
CODE_CELL_RED_SUPER = 2
CODE_CELL_BLUE_PLAIN = 3
CODE_CELL_BLUE_SUPER = 4
CODE_BUTTON_RED_GOAL = 7
CODE_BUTTON_RED_UNDO = 8
CODE_BUTTON_BLUE_GOAL = 5
CODE_BUTTON_BLUE_UNDO = 6

IGNORE_CODES = []

allowed_IPs = ['127.0.0.1']


def timezone():
    t = int(time.time())
    return (t % 10 < 5)


# From https://docs.python.org/2/library/socketserver.html#asynchronous-mixins
class Connection(SocketServer.BaseRequestHandler):
    def handle(self):
        # TODO: print peer name
        print >> sys.stderr, "Connection received"
        addr = self.client_address
        print >> sys.stderr, addr
        global running, core, core_lock, allowed_IPs
        if addr[0] not in allowed_IPs:
            print >> sys.stderr, "shutting down", allowed_IPs
            self.request.shutdown(socket.SHUT_RDWR)
            return
        fd = self.request.makefile('r+b', 0)
        actions = {
            CODE_NOOP: lambda: None,
            CODE_CELL_RED_PLAIN: core.easy_act_red_goal_cell,
            CODE_CELL_RED_SUPER: core.easy_act_red_supergoal_cell,
            CODE_CELL_BLUE_PLAIN: core.easy_act_blue_goal_cell,
            CODE_CELL_BLUE_SUPER: core.easy_act_blue_supergoal_cell,
            CODE_BUTTON_RED_GOAL: core.easy_act_red_goal_button,
            CODE_BUTTON_RED_UNDO: core.easy_act_red_goalundo_button,
            CODE_BUTTON_BLUE_GOAL: core.easy_act_blue_goal_button,
            CODE_BUTTON_BLUE_UNDO: core.easy_act_blue_goalundo_button,
            }
        last_gol = time.time()
        while running:
            ready_r, ready_w, ready_x = select.select([fd], [], [], 1.0)
            if fd in ready_r:
                code_str = fd.read(1)
                if code_str == '':
                    break
                code = ord(code_str)
                print >> sys.stderr, "Received code: %d" % (code)
                if code not in IGNORE_CODES:
                    with core_lock:
                        try:
                            if time.time()-last_gol > 0.8:
                                if dry_run:
                                    print >> sys.stdout, "fun: %s" % str(actions[code])
                                else:
                                    actions[code]()
                                if(code != 0):
                                    last_gol = time.time()
                        except KeyError:
                            print >> sys.stderr, "Wrong code"
                else:
                    print >> sys.stderr, "Ignore command because of configuration"
            with core_lock:
                core.update()
            if (time.time()-last_gol) < 5:
                red_score = core.easy_get_red_part()
                blue_score = core.easy_get_blue_part()
            else:
                red_score = core.easy_get_red_score()
                blue_score = core.easy_get_blue_score()
            print >> sys.stdout, red_score, blue_score
            fd.write(struct.pack(">HH", red_score, blue_score))
        fd.close()
        self.request.shutdown(socket.SHUT_RDWR)
        print >> sys.stderr, "Connection closed"


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


def main():
    global running, core, core_lock, allowed_IPs, dry_run

    parser = argparse.ArgumentParser(description='Arduino interface')
    parser.add_argument('match_id', type=int, help='The id of the match to connect to')
    parser.add_argument('--listen_addr', default='0.0.0.0', help='The address the listener server listens to')
    parser.add_argument('--listen_port', default=2204, type=int, help='The address the listener server listens to')
    parser.add_argument('arduino_ip', help='The ip of the allowed Arduino')
    parser.add_argument('--dry-run', action='store_true', help='Test run')

    args = parser.parse_args()

    allowed_IPs.append(args.arduino_ip)
    dry_run = args.dry_run

    core = SubottoCore(args.match_id)
    with core_lock:
        core.update()

    # Initialize ConnectionServer
    server = ThreadedTCPServer((args.listen_addr, args.listen_port), Connection)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    print >> sys.stdout, "Started server on {}:{}".format(args.listen_addr, args.listen_port)

    # Do things
    try:
        while True:
            with core_lock:
                core.update()
            time.sleep(1.0)
    except KeyboardInterrupt:
        running = False

    running = False
    server.shutdown()
    server.server_close()
    server_thread.join()


if __name__ == '__main__':
    main()

#!/usr/bin/env python
'''The main entry point. Invoke as `switchboard' or `python -m switchboard'.

'''

import argparse
import sys

from switchboard.config import SwitchboardConfig
from switchboard.ws_ctrl_server import WSCtrlServer
from switchboard.engine import SwitchboardEngine
from switchboard.app_manager import AppManager
from switchboard.cli import SwitchboardCli
from switchboard.log import init_logging


def main():
    try:
        arg_parser = argparse.ArgumentParser()
        arg_parser.add_argument('-c', '--config', help='specify .json config file')
        args = arg_parser.parse_args()

        swb_config = SwitchboardConfig()
        if args.config:
            swb_config.load_config(args.config)

        init_logging(swb_config)

        ws_ctrl_server = WSCtrlServer(swb_config)
        swb = SwitchboardEngine(swb_config, ws_ctrl_server)

        with AppManager(swb_config, swb) as app_manager:
            cli = SwitchboardCli(swb, swb_config, app_manager)
            ws_ctrl_server.init_config()

            if args.config:
                swb.init_clients()

                # Only once the clients have been setup can we initialise the app manager
                app_manager.init_config()

                # And the modules go right at the end once we know all the devices
                swb.init_modules()

            ws_ctrl_server.set_dependencies(swb, app_manager)
            swb.start()
            sys.exit(cli.run())

    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

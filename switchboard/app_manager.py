
import os
import sys
import time
import json
import signal
import requests
from subprocess import Popen, PIPE

from switchboard.utils import get_input, get_free_port
from switchboard.engine import EngineError
from apps.app_list import APP_LIST

def format_arg(arg_info, value):
    return ' {} {}'.format(arg_info['args'][0], value)

class AppManager:
    def __init__(self, configs, swb):
        self._configs = configs
        self._swb = swb
        self.apps_running = {}

    def init_config(self):
        for app, app_configs in self._configs.get('apps').items():
            print('Starting ' + app)
            if not self._execute_app(app, app_configs):
                print('Unable to start app "{}". Please fix config file and restart'.format(app))
                sys.exit(1)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        for pid in self.apps_running.values():
            self._terminate(pid)

    def _terminate(self, pid):
        os.killpg(os.getpgid(pid), signal.SIGTERM)

    def kill(self, app):
        if not app in self.apps_running:
            print('Cannot kill {} app as it was not launched by Switchboard'.format(app))
            return

        self._terminate(self.apps_running[app])

    def launch(self, app):
        # Get the required config options for this app
        p = Popen(app + ' --getconf', shell=True, stdout=PIPE, preexec_fn=os.setsid)
        time.sleep(0.1)

        if not p.poll() == None:
            self._terminate(p.pid)
            print('Error: app hangs when getting config options')
            return

        output, error = p.communicate()

        if error:
            print('Error: app encountered an error')
            return

        # If the app is a Switchboard client we connect to it automatically
        client_port = None
        app_configs = {}

        # Determine app args and populate them
        try:
            args = json.loads(output)
        except:
            print('Unable to parse app config definitions')
            return

        command = app
        for name, arg_info in args.items():
            # Pre-populate as many arguments as possible...
            if name == 'IOData port':
                command += format_arg(arg_info, self._configs.get('iodata_port'))
            elif name == 'IOData host':
                command += format_arg(arg_info, 'localhost')
            elif name == 'Client port':
                client_port = get_free_port()
                command += format_arg(arg_info, client_port)
            elif name == 'autokill':
                command += ' --autokill'
            else:
                # ...for every other argument prompt the user
                kwargs = arg_info['kwargs']
                help = kwargs['help']

                if 'action' in kwargs and kwargs['action'] in 'store_true':
                    while True:
                        value = get_input('{}? [y/n] '.format(help))
                        value = value.lower()
                        if not value in [ 'y', 'n' ]:
                            print('Invalid input')
                            continue
                        if value == 'y':
                            command += ' ' + arg_info['args'][0]
                        break
                else:
                    if 'default' in kwargs:
                        default = ' [{}]'.format(kwargs['default'])
                        value = get_input('Please enter a value for the {}{}: '.format(help, default))
                        if value:
                            command += format_arg(arg_info, value)
                    else:
                        value = get_input('Please enter a value for the {}: '.format(help))
                        command += format_arg(arg_info, value)

        app_configs['command'] = command

        # If this is a client app we need to add the host
        if client_port:
            app_configs['client_port'] = client_port
            alias = get_input('Please enter a host alias for this client: ')
            app_configs['host_alias'] = alias

        if self._execute_app(app, app_configs):
            self._configs.add_app(app, app_configs)

    def _execute_app(self, app, app_configs):
        # Launch the app and make sure it hasn't crashed on us
        p = Popen(app_configs['command'], shell=True, preexec_fn=os.setsid)
        time.sleep(0.1)
        if not p.poll() == None:
            print('App has terminated unexpectedly with command: {}'.format(command))
            return False

        self.apps_running[app] = p.pid

        if 'client_port' in app_configs or 'host_alias' in app_configs:
            if 'client_port' in app_configs and 'host_alias' in app_configs:
                remaining_attempts = 5
                error = ''
                url = 'http://localhost:' + str(app_configs['client_port'])

                # First check if the server has started up and if it has add the host
                while remaining_attempts:
                    try:
                        requests.get(url + '/devices_info')
                        break
                    except Exception as e:
                        error = e
                        remaining_attempts -= 1
                        time.sleep(1)

                if remaining_attempts == 0:
                    print('Unable to connect to app host {}: {}'.format(url, error))
                    return False

                self._swb.add_host(url, app_configs['host_alias'])

            else:
                # This error should only really happen if the config file is corrupted
                print('Cannot add host, client_port or host_alias not defined')
                sys.exit(1)

        return True
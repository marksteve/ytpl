import json
import os


DEV_SERVER_HOST = 'localhost'
DEV_SERVER_PORT = 34897
ENVIRON_FILE = '/home/dotcloud/environment.json'


if os.path.exists(ENVIRON_FILE):
  debug = False
  with open(ENVIRON_FILE) as f:
    env = json.load(f)
else:
  debug = True
  env = os.environ

mod_path = os.path.dirname(__file__)
root_url = env.get('PROD_SERVER_URL', 'http://%s:%s' % (DEV_SERVER_HOST, DEV_SERVER_PORT)).rstrip('/')

# Gunicorn config
bind = '%s:%s' % (DEV_SERVER_HOST, DEV_SERVER_PORT)
worker_class = 'ytpl.GeventWebSocketWorker'

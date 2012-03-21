from fboauth2 import FBClient
from mako.template import Template
import cherrypy
import json
import os
import redis
import requests
import urllib
import uuid


DEV_SERVER_HOST = 'localhost'
DEV_SERVER_PORT = 34897

YT_SEARCH_URL = 'https://gdata.youtube.com/feeds/api/videos?q=%s&orderby=relevance&max-results=10&v=2&alt=json'

ENVIRON_FILE = '/home/dotcloud/environment.json'

if os.path.exists(ENVIRON_FILE):
  with open(ENVIRON_FILE) as f:
    env = json.load(f)
else:
  env = os.environ

root_url = env.get('DOTCLOUD_WWW_HTTP_URL', 'http://%s:%d/' % (DEV_SERVER_HOST, DEV_SERVER_PORT))
root_url = root_url.rstrip('/')

mod_path = os.path.dirname(__file__)


class YTPL:
  def __init__(self):
    self.redis = redis.Redis(
      host=env.get('DOTCLOUD_DATA_REDIS_HOST', 'localhost'),
      password=env.get('DOTCLOUD_DATA_REDIS_PASSWORD', None),
      port=int(env.get('DOTCLOUD_DATA_REDIS_PORT', 6379)),
    )

  @property
  def sess(self):
    return cherrypy.session

  @property
  def fbclient(self):
    return self.sess.get('fbclient')

  @property
  def user(self):
    return self.sess.get('user')

  @cherrypy.expose
  def index(self):
    t = Template(filename=os.path.join(mod_path, 'index.html'))
    return t.render(signed_in=hasattr(self.fbclient, 'access_token') and self.user, user=self.user)

  @cherrypy.expose
  def fbsignin(self):
    self.fbclient = FBClient(env.get('FB_CLIENT_ID'), env.get('FB_CLIENT_SECRET'),
                             'publish_stream', root_url + '/fboauth')
    raise cherrypy.HTTPRedirect(self.fbclient.get_auth_url())

  @cherrypy.expose
  def fboauth(self, code):
    self.fbclient.get_access_token(code)
    self.user = self.fbclient.graph_request('me')
    raise cherrypy.HTTPRedirect('/')

  @cherrypy.expose
  @cherrypy.tools.json_out(on=True)
  def new(self):
    while True:
      pl_name = uuid.uuid1().hex[:8]
      if not self.redis.exists(pl_name):
        break

    self.redis.set('creator:%s' % pl_name, self.user['id'])

    return {
      'name': pl_name,
    }

  @cherrypy.expose
  @cherrypy.tools.json_in(on=True)
  @cherrypy.tools.json_out(on=True)
  def default(self, pl_name, id=None):
    if self.redis.get('creator:%s' % pl_name) != self.user['id']:
      raise cherrypy.HTTPError(401)

    req = cherrypy.request
    pl_key = 'pl:%s' % pl_name

    if req.method == 'PUT':
      video = cherrypy.request.json

      del video['id'] # Don't store in video info
      vid = video['vid']

      # Store vid reference
      self.redis.hset('id_vid:%s' % pl_name, id, vid)

      # Store vid info
      self.redis.set('vid:%s' % vid, '%s:%s' % (vid, json.dumps(video)))

      # Get new entry index
      pos = self.redis.llen(pl_key)

      # Push to playlist
      self.redis.rpush(pl_key, id)

      video['pos'] = pos

      return video

    elif req.method == 'DELETE':
      if id:
        self.redis.lrem(pl_key, id)
      else: # Clear all
        self.redis.ltrim(pl_key, 1, -1)

    videos = []

    # Get references
    id_vid = self.redis.hgetall('id_vid:%s' % pl_name)
    vid_infos = {}

    # Get vids from references
    vids = ['vid:%s' % vid for vid in id_vid.values()]
    if vids:
      # Get vid info
      for vid_info in self.redis.mget(vids):
        vid, info = vid_info.split(':', 1)
        vid_infos[vid] = json.loads(info)

      # Fill playlist items with vid info
      for pos, id in enumerate(self.redis.lrange(pl_key, 0, -1)):
        vid_info = vid_infos[id_vid[id]]
        vid_info.update({
          'id': id,
          'pos': pos,
        })
        videos.append(vid_info)

    return {
      'name': pl_name,
      'videos': videos,
    }

  @cherrypy.expose
  @cherrypy.tools.json_out(on=True)
  def search(self, q):
    q = urllib.quote_plus(q)
    if not q:
      return []
    r = requests.get(YT_SEARCH_URL % q)
    feed = json.loads(r.text).get('feed')
    results = []
    for e in feed['entry']:
      results.append({
        'id': uuid.uuid4().hex,
        'vid': e['media$group']['yt$videoid']['$t'],
        'author': e['author'][0]['name']['$t'],
        'title': e['title']['$t'],
        'thumbnail': [t for t in e['media$group']['media$thumbnail'] if t['yt$name'] == 'hqdefault'][0],
      })
    return results


def setup_server():
  cherrypy.config.update({
    'tools.sessions.on': True,
  })


def start():
  setup_server()
  app = cherrypy.Application(YTPL())
  app.merge({
    '/static': {
      'tools.staticdir.on': True,
      'tools.staticdir.dir': os.path.join(mod_path, 'static'),
    }
  })
  cherrypy.server.socket_host = DEV_SERVER_HOST
  cherrypy.server.socket_port = DEV_SERVER_PORT
  cherrypy.quickstart(app)

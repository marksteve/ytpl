from fboauth2 import FBClient
from mako.template import Template
import cherrypy
import json
import os
import redis
import requests
import urllib


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


def randstr(l=8):
  return os.urandom(l / 2).encode('hex')


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
  def req(self):
    return cherrypy.request

  @property
  def user(self):
    return self.sess.get('user')

  def get_fbclient(self):
    kwargs = {
      'scope': 'publish_stream',
      'redirect_uri': root_url + '/fboauth',
    }
    access_token = self.sess.get('access_token')
    if access_token:
      kwargs['access_token'] = access_token
    return FBClient(env.get('FB_CLIENT_ID'), env.get('FB_CLIENT_SECRET'), **kwargs)

  @cherrypy.expose
  def index(self):
    t = Template(filename=os.path.join(mod_path, 'about.html'))
    user = self.sess.get('user')
    return t.render(user=user)

  @cherrypy.expose
  def default(self, pl_name):
    t = Template(filename=os.path.join(mod_path, 'playlist.html'))
    user = self.sess.get('user')
    is_creator = user and self.redis.get('creator:%s' % pl_name) == user['id']
    return t.render(user=user, is_creator=is_creator)

  @cherrypy.expose
  def fbsignin(self):
    fbclient = self.get_fbclient()
    raise cherrypy.HTTPRedirect(fbclient.get_auth_url())

  @cherrypy.expose
  def fbsignout(self):
    cherrypy.lib.sessions.expire()
    raise cherrypy.HTTPRedirect('/')

  @cherrypy.expose
  def fboauth(self, code):
    fbclient = self.get_fbclient()
    access_token = fbclient.get_access_token(code)
    self.sess['user'] = fbclient.graph_request('me')
    self.sess['access_token'] = access_token
    raise cherrypy.HTTPRedirect('/new')

  @cherrypy.expose
  @cherrypy.tools.json_out(on=True)
  def new(self):
    if not self.user:
      raise cherrypy.HTTPRedirect('fbsignin')

    while True:
      pl_name = randstr(8)
      if not self.redis.exists(pl_name):
        break

    self.redis.set('creator:%s' % pl_name, self.user['id'])

    raise cherrypy.HTTPRedirect(pl_name)

  @cherrypy.expose
  @cherrypy.tools.json_in(on=True)
  @cherrypy.tools.json_out(on=True)
  def pl(self, pl_name, id=None):
    if (self.req.method != 'GET' # modify playlist
        and (not self.user # not signed in
             or self.redis.get('creator:%s' % pl_name) != self.user['id'])): # not owner
      raise cherrypy.HTTPError(401)

    pl_key = 'pl:%s' % pl_name

    if self.req.method == 'PUT':
      video = self.req.json

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

    elif self.req.method == 'DELETE':
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
        'id': randstr(12),
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

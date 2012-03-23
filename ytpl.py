from fboauth2 import FBClient
from mako.template import Template
import cherrypy
import cherrys
import json
import os
import random
import redis
import requests
import urllib

cherrypy.lib.sessions.RedisSession = cherrys.RedisSession


DEV_SERVER_HOST = 'localhost'
DEV_SERVER_PORT = 34897

YT_SEARCH_URL = 'https://gdata.youtube.com/feeds/api/videos?q=%s&orderby=relevance&max-results=10&v=2&alt=json'

ENVIRON_FILE = '/home/dotcloud/environment.json'

if os.path.exists(ENVIRON_FILE):
  with open(ENVIRON_FILE) as f:
    env = json.load(f)
else:
  env = os.environ

root_url = env.get('PROD_SERVER_HOST', 'http://%s:%d/' % (DEV_SERVER_HOST, DEV_SERVER_PORT))
root_url = root_url.rstrip('/')

mod_path = os.path.dirname(__file__)


def randstr(l=8):
  return os.urandom(l / 2).encode('hex')


class YTPL:
  def __init__(self):
    self.redis = redis.Redis(
      host=env.get('DOTCLOUD_DATA_REDIS_HOST', 'localhost'),
      password=env.get('DOTCLOUD_DATA_REDIS_PASSWORD'),
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
  def fbsignin(self, pl_name=None):
    fbclient = self.get_fbclient()
    raise cherrypy.HTTPRedirect(fbclient.get_auth_url(state=pl_name))

  @cherrypy.expose
  def fboauth(self, code, state=None):
    fbclient = self.get_fbclient()
    access_token = fbclient.get_access_token(code)
    self.sess['user'] = fbclient.graph_request('me')
    self.sess['access_token'] = access_token
    if state:
      raise cherrypy.HTTPRedirect('/' + state)
    else:
      raise cherrypy.HTTPRedirect('/new')

  @cherrypy.expose
  def fbsignout(self):
    cherrypy.lib.sessions.expire()
    raise cherrypy.HTTPRedirect('/')

  @cherrypy.expose
  def index(self):
    t = Template(filename=os.path.join(mod_path, 'index.html'))
    user = self.sess.get('user')
    return t.render(user=user)

  @cherrypy.expose
  def new(self):
    if not self.user:
      raise cherrypy.HTTPRedirect('fbsignin')

    while True:
      pl_name = randstr(8)
      if not self.redis.exists('pl:%s' % pl_name):
        break

    raise cherrypy.HTTPRedirect(pl_name)

  @cherrypy.expose
  def random(self):
    top_pls = self.redis.zrevrange('plviews', 0, 100)
    raise cherrypy.HTTPRedirect('/' + random.choice(top_pls))

  @cherrypy.expose
  def default(self, pl_name):
    t = Template(filename=os.path.join(mod_path, 'playlist.html'))
    creator_key = 'creator:%s' % pl_name
    pls_key = 'pls:%s' % self.user['id'] if self.user else None

    # create if new
    if self.user and not self.redis.exists('pl:%s' % pl_name):
      # set creator id
      self.redis.set(creator_key, self.user['id'])

      # push playlist name to user's playlists for querying later
      self.redis.sadd(pls_key, pl_name)

      can_edit = True

    else:
      can_edit = self.user and self.redis.get(creator_key) == self.user['id']

    playlists = self.redis.smembers(pls_key) if pls_key else []

    # Increment views
    viewed_key = 'viewed:%s' % pl_name
    # Should have at least 1 video and only once per user session
    if self.redis.zcard('pl:%s' % pl_name) > 0 and not self.sess.get(viewed_key, False):
      self.redis.zincrby('plviews', pl_name, 1)
      self.sess[viewed_key] = True

    # TODO: Add whitelist editors

    return t.render(user=self.user, pl_name=pl_name, can_edit=can_edit, playlists=playlists)

  @cherrypy.expose
  @cherrypy.tools.json_in(on=True)
  @cherrypy.tools.json_out(on=True)
  def pl(self, pl_name, id=None):
    pl_key = 'pl:%s' % pl_name
    creator_key = 'creator:%s' % pl_name

    # check permissions
    if self.user and self.redis.get(creator_key) == self.user['id']:
      pass
    # if unauthorized and tried to modify...
    elif self.req.method != 'GET':
      raise cherrypy.HTTPError(401)

    if self.req.method == 'POST':
      video = self.req.json

      id = randstr(12)
      vid = video['vid']

      # Store vid reference
      self.redis.hset('id_vid:%s' % pl_name, id, vid)

      # Store vid info
      self.redis.set('vid:%s' % vid, '%s:%s' % (vid, json.dumps(video)))

      # Get new entry index
      pos = self.redis.zcard(pl_key)

      # Push to playlist
      self.redis.zadd(pl_key, **{id: pos})

      video.update({
        'id': id,
        'pos': pos,
      })

      return video

    elif self.req.method == 'DELETE':
      if id:
        self.redis.zrem(pl_key, id)
      else: # Clear all
        self.redis.zremrangebyrank(pl_key, 0, -1)

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
      for pos, id in enumerate(self.redis.zrange(pl_key, 0, -1)):
        vid_info = dict(vid_infos[id_vid[id]])
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
        'vid': e['media$group']['yt$videoid']['$t'],
        'author': e['author'][0]['name']['$t'],
        'title': e['title']['$t'],
        'thumbnail': [t for t in e['media$group']['media$thumbnail'] if t['yt$name'] == 'hqdefault'][0],
      })
    return results


def setup_server():
  cherrypy.config.update({
    'tools.sessions.on': True,
    'tools.sessions.storage_type': 'redis',
    'tools.sessions.host': env.get('DOTCLOUD_DATA_REDIS_HOST', 'localhost'),
    'tools.sessions.port': int(env.get('DOTCLOUD_DATA_REDIS_PORT', 6379)),
    'tools.sessions.db': 0,
    'tools.sessions.password': env.get('DOTCLOUD_DATA_REDIS_PASSWORD'),
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

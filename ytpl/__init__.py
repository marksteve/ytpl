from gdata.client import GDClient, RequestError
from gdata.gauth import AUTH_SCOPES, OAuth2Token, OAuth2AccessTokenError
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

USERINFO_SCOPE = 'https://www.googleapis.com/auth/userinfo.profile'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v1/userinfo'

ENVIRON_FILE = '/home/dotcloud/environment.json'

if os.path.exists(ENVIRON_FILE):
  with open(ENVIRON_FILE) as f:
    env = json.load(f)
else:
  env = os.environ

package_path = os.path.dirname(__file__)


class YTPL:
  def __init__(self):
    self.redis = redis.Redis(
      host=env.get('DOTCLOUD_DATA_REDIS_HOST', 'localhost'),
      password=env.get('DOTCLOUD_DATA_REDIS_PASSWORD', None),
      port=int(env.get('DOTCLOUD_DATA_REDIS_PORT', 6379)),
    )
    self.root_url = env.get('DOTCLOUD_WWW_HTTP_URL',
                            'http://%s:%d/' % (DEV_SERVER_HOST, DEV_SERVER_PORT))
    self.oauth_callback_url = self.root_url + 'oauth2callback'

  def _create_token(self, **kwargs):
    scopes = list(AUTH_SCOPES['youtube'])
    scopes.append(USERINFO_SCOPE)
    token = OAuth2Token(env['GOOGLE_CLIENT_ID'], env['GOOGLE_CLIENT_SECRET'],
                        scope=' '.join(scopes), user_agent='YTPL')
    token.redirect_uri = self.oauth_callback_url
    return token

  @cherrypy.expose
  def index(self):
    if cherrypy.session.get('user_id'):
      t = Template(filename=os.path.join(package_path, 'index.html'))
      return t.render()
    else:
      raise cherrypy.HTTPRedirect('/signin')

  @cherrypy.expose
  def signin(self, force=None):
    token = self._create_token()
    params = {}
    if force == 'true':
      params['approval_prompt'] = 'force'
    token_auth_url = token.generate_authorize_url(self.oauth_callback_url, access_type='offline',
                                                  **params)
    raise cherrypy.HTTPRedirect(token_auth_url)

  @cherrypy.expose
  def oauth2callback(self, code):
    token = self._create_token()

    def force_signin():
      raise cherrypy.HTTPRedirect('/signin?force=true')

    try:
      token = token.get_access_token(code)
    except OAuth2AccessTokenError:
      force_signin()

    client = token.authorize(GDClient(source=token.user_agent))

    try:
      userinfo = json.loads(client.request('GET', USERINFO_URL).read())
    except RequestError:
      force_signin()

    user_id = userinfo['id']
    token_key = 'token:%s' % user_id

    if not self.redis.exists(token_key):
      refresh_token = token.refresh_token
      if refresh_token:
        self.redis.set(token_key, refresh_token)
      else:
        force_signin()

    cherrypy.session['user_id'] = user_id

    raise cherrypy.HTTPRedirect('/')

  @cherrypy.expose
  @cherrypy.tools.json_out(on=True)
  def new(self):
    while True:
      pl_name = uuid.uuid1().hex[:8]
      if not self.redis.exists(pl_name):
        break
    return {
      'name': pl_name,
    }

  @cherrypy.expose
  @cherrypy.tools.json_in(on=True)
  @cherrypy.tools.json_out(on=True)
  def default(self, pl_name, id=None):
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
      'tools.staticdir.dir': os.path.join(os.path.dirname(package_path), 'static'),
    }
  })
  cherrypy.server.socket_host = DEV_SERVER_HOST
  cherrypy.server.socket_port = DEV_SERVER_PORT
  cherrypy.quickstart(app)

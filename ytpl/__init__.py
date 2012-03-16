from mako.template import Template
import cherrypy
import json
import os
import redis
import requests
import urllib
import uuid


YT_SEARCH_URL = 'https://gdata.youtube.com/feeds/api/videos?q=%s&orderby=relevance&max-results=10&v=2&alt=json'
ENVIRON_FILE = '/home/dotcloud/environment.json'


package_path = os.path.dirname(__file__)


class YTPL:
  def __init__(self):
    if os.path.exists(ENVIRON_FILE):
      with open(ENVIRON_FILE) as f:
        environment = json.load(f)
      self.redis = redis.Redis(
        host=environment['DOTCLOUD_DATA_REDIS_HOST'],
        password=environment['DOTCLOUD_DATA_REDIS_PASSWORD'],
        port=int(environment['DOTCLOUD_DATA_REDIS_PORT']),
      )
    else:
      self.redis = redis.Redis()

  @cherrypy.expose
  def index(self):
    t = Template(filename=os.path.join(package_path, 'index.html'))
    return t.render()

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


def start():
  app = cherrypy.Application(YTPL())
  app.merge({
    '/static': {
      'tools.staticdir.on': True,
      'tools.staticdir.dir': os.path.join(os.path.dirname(package_path), 'static'),
    }
  })
  cherrypy.server.socket_port = 25347
  cherrypy.quickstart(app)

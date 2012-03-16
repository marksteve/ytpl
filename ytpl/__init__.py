from mako.template import Template
import cherrypy
import json
import os
import redis
import requests
import urllib
import uuid


YT_SEARCH_URL = 'https://gdata.youtube.com/feeds/api/videos?q=%s&orderby=relevance&max-results=10&v=2&alt=json'


package_path = os.path.dirname(__file__)


class YTDJ:
  def __init__(self):
    self.redis = redis.Redis()

  @cherrypy.expose
  def index(self):
    t = Template(filename=os.path.join(package_path, 'index.html'))
    return t.render()

  @cherrypy.expose
  @cherrypy.tools.json_out(on=True)
  def new(self):
    return {
      'name': uuid.uuid1().hex,
    }

  @cherrypy.expose
  @cherrypy.tools.json_in(on=True)
  @cherrypy.tools.json_out(on=True)
  def default(self, pl_name, action=None, song_id_or_idx=None):
    if action:

      if action == 'add':
        self.redis.rpush(pl_name, json.dumps(cherrypy.request.json))

      elif action == 'clear':
        self.redis.ltrim(pl_name, 1, 0)

    return {
      'name': pl_name,
      'songs': [json.loads(s) for s in self.redis.lrange(pl_name, 0, -1)],
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
  app = cherrypy.Application(YTDJ())
  app.merge({
    '/res': {
      'tools.staticdir.on': True,
      'tools.staticdir.dir': os.path.join(package_path, 'res'),
    }
  })
  cherrypy.server.socket_port = 25347
  cherrypy.quickstart(app)

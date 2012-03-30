from gevent import monkey
monkey.patch_all()
from datetime import datetime
from fboauth2 import FBClient
from flask import Flask, request, session, redirect, abort, jsonify
from geventwebsocket.handler import WebSocketHandler
from gunicorn.workers.ggevent import GeventPyWSGIWorker
from mako.template import Template
import config
import gevent
import json
import os
import random
import redis


def randstr(l=8):
  return os.urandom(l / 2).encode('hex')


app = Flask(__name__)
app.secret_key = str(config.env.get('SESSION_SECRET_KEY', 'mKzS85NhkAzFDGLRdM4pNQsIK2Png5u897asjk'))
app.debug = config.debug


r = redis.Redis(
  host=config.env.get('DOTCLOUD_DATA_REDIS_HOST', 'localhost'),
  password=config.env.get('DOTCLOUD_DATA_REDIS_PASSWORD'),
  port=int(config.env.get('DOTCLOUD_DATA_REDIS_PORT', 6379)),
)


def get_fbclient():
  fbclient_kwargs = {
    'scope': 'publish_stream',
    'redirect_uri': config.root_url + '/fboauth',
  }
  access_token = session.get('access_token')
  if access_token:
    fbclient_kwargs['access_token'] = access_token
  return FBClient(config.env.get('FB_CLIENT_ID'), config.env.get('FB_CLIENT_SECRET'),
                  **fbclient_kwargs)


def get_videos(pl_name, start=0, end=-1):
  videos = []

  # Get references
  id_vid = r.hgetall('id_vid:%s' % pl_name)
  vid_infos = {}

  # Get vids from references
  vids = ['vid:%s' % vid for vid in id_vid.values()]
  if vids:
    # Get vid info
    for vid_info in r.mget(vids):
      vid, info = vid_info.split(':', 1)
      vid_infos[vid] = json.loads(info)

    # Fill playlist items with vid info
    for id, pos in r.zrange('pl:%s' % pl_name, start, end, withscores=True):
      pos = int(pos)
      vid_info = dict(vid_infos[id_vid[id]])
      vid_info.update({
        'id': id,
        'pos': pos,
      })
      videos.append(vid_info)

  return videos


def resort_videos(pl_key):
  with r.pipeline() as pipe:
    while True:
      try:
        updated = {}
        pipe.watch(pl_key)
        for pos, id in enumerate(pipe.zrange(pl_key, 0, -1)):
          updated[id] = pos
        pipe.multi()
        if updated:
          for id, pos in updated.items():
            pipe.zadd(pl_key, id, pos)
        pipe.execute()
        break
      except redis.exceptions.WatchError:
        # Retry
        continue


@app.route('/')
def index():
  t = Template(filename=os.path.join(config.mod_path, 'index.html'))
  user = session.get('user')
  return t.render(user=user)


@app.route('/<pl_name>')
def playlist(pl_name):
  t = Template(filename=os.path.join(config.mod_path, 'playlist.html'))
  creator_key = 'creator:%s' % pl_name
  pls_key = 'pls:%s' % session['user']['id'] if session.get('user') else None

  # Title
  title = 'YTPL - %s' % pl_name

  # Open Graph
  og = {}
  videos = get_videos(pl_name, end=9)
  if videos:
    vid_info = videos[0]
    og.update({
      'type': 'website',
      'url': '%s/%s' % (config.root_url, pl_name),
      'image': vid_info['thumbnail']['url'],
      'title': title,
      'description': '\n'.join(["%d. %s - %s" % (i + 1, v['title'], v['author'])
                               for i, v in enumerate(videos)])[:250] + '...',
    })

  can_edit = False

  # Get permissions
  if r.exists('pl:%s' % pl_name):
    can_edit = session.get('user') and r.get(creator_key) == session['user']['id']

  # create if new
  else:

    if session.get('user'):
      # set creator id
      r.set(creator_key, session['user']['id'])

      # push playlist name to user's playlists for querying later
      r.sadd(pls_key, pl_name)

      can_edit = True

    else:
      return redirect('/fbsignin?pl_name=%s' % pl_name)

  playlists = r.smembers(pls_key) if pls_key else []

  # Increment views
  viewed_key = 'viewed:%s' % pl_name
  # Should have at least 1 video and only once per user session
  if r.zcard('pl:%s' % pl_name) > 0 and not session.get(viewed_key, False):
    r.zincrby('plviews', pl_name, 1)
    session[viewed_key] = True

  # TODO: Add whitelist editors

  return t.render(user=session.get('user'), pl_name=pl_name, og=og, title=title, can_edit=can_edit,
                  playlists=playlists, debug=config.debug, ws_url=config.ws_url)


@app.route('/pl/<pl_name>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/pl/<pl_name>/<id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def pl(pl_name, id=None):
  pl_key = 'pl:%s' % pl_name
  creator_key = 'creator:%s' % pl_name
  id_vid_key = 'id_vid:%s' % pl_name

  # check permissions
  if session.get('user') and r.get(creator_key) == session['user']['id']:
    pass
  # if unauthorized and tried to modify...
  elif request.method != 'GET':
    abort(401)

  if request.method == 'POST':
    video = request.json

    while True:
      id = randstr(12)
      if not r.hexists(id_vid_key, id):
        break
    vid = video['vid']

    # Store vid reference
    r.hset(id_vid_key, id, vid)

    # Store vid info
    r.set('vid:%s' % vid, '%s:%s' % (vid, json.dumps(video)))

    # Get new entry index
    pos = r.zcard(pl_key)

    # Push to playlist
    r.zadd(pl_key, id, pos)

    video.update({
      'id': id,
      'pos': pos,
    })

    # Let other viewers know what changed
    r.publish('plrt:%s' % pl_name, '%s:pl_add:%s' % (session['user']['id'], json.dumps({
      'video': video,
    })))

    return jsonify(**video)

  elif request.method == 'PUT':
    video = request.json
    old_pos = r.zrank(pl_key, id)
    new_pos = int(video['pos'])
    asc = new_pos - old_pos > 0
    r.zadd(pl_key, id, float(new_pos + (0.5 if asc else -0.5)))
    resort_videos(pl_key)

  elif request.method == 'DELETE':
    if id:
      r.zrem(pl_key, id)
      resort_videos(pl_key)
    else:
      # Clear all
      r.zremrangebyrank(pl_key, 0, -1)

  videos = get_videos(pl_name)

  if request.method in ('PUT', 'DELETE'):
    # Let other viewers know what changed
    r.publish('plrt:%s' % pl_name, '%s:pl_reset:%s' % (session['user']['id'], json.dumps({
      'videos': videos,
    })))

  return jsonify(videos=get_videos(pl_name))


@app.route('/share/<pl_name>')
@app.route('/share/<pl_name>/<message>')
def share(pl_name, message=None):
  if r.zcard('pl:%s' % pl_name) > 0:
    data = {'link': '%s/%s' % (config.root_url, pl_name)}
    if message:
      data['message'] = message
    fbclient = get_fbclient()
    fbclient.graph_request('me/links', method='post', data=data)
  else:
    abort(400, 'Playlist is empty')


@app.route('/new')
def new():
  if not session.get('user'):
    return redirect('fbsignin')

  while True:
    pl_name = randstr(8)
    if not r.exists('pl:%s' % pl_name):
      break

  return redirect(pl_name)


@app.route('/random')
def random():
  top_pls = r.zrevrange('plviews', 0, 100)
  return redirect('/' + random.choice(top_pls))


@app.route('/fbsignin')
@app.route('/fbsignin/<pl_name>')
def fbsignin(pl_name=None):
  fbclient = get_fbclient()
  return redirect(fbclient.get_auth_url(state=pl_name))


@app.route('/fboauth')
def fboauth():
  code = request.args.get('code')
  state = request.args.get('state')
  fbclient = get_fbclient()
  access_token = fbclient.get_access_token(code)
  session['user'] = fbclient.graph_request('me')
  session['access_token'] = access_token
  if state:
    return redirect('/' + state)
  else:
    pl_name = r.srandmember('pls:%s' % session['user']['id'])
    if pl_name:
      return redirect('/' + pl_name)
    else:
      return redirect('/new')


@app.route('/fbsignout')
def fbsignout():
  session.pop('user')
  session.pop('access_token')
  return redirect('/')


def changes_publisher(pl_name, ws, user_id):
  # Relay changes from redis pubsub
  client = r.pubsub()
  client.subscribe('plrt:%s' % pl_name)

  for message in client.listen():
    msg_user_id, data = message['data'].split(':', 1)

    # Don't send message to self
    if msg_user_id == user_id:
      continue

    ws.send(data)


@app.route('/ws')
def ws():
  ws = request.environ.get('wsgi.websocket')
  if ws:
    user = session.get('user')
    if user:
      user = dict([(n, user[n]) for n in ('id', 'name', 'username')])
    else:
      user = {'id': randstr(24), 'name': 'Anonymous', 'username': None}

    user_id = user['id']

    # Initial message should be playlist name
    pl_name = None
    while not pl_name:
      pl_name = ws.receive()

    plls_key = 'plls:%s' % pl_name
    plrt_key = 'plrt:%s' % pl_name
    ol_key = 'ol:%s' % user_id

    publisher = gevent.spawn(changes_publisher, pl_name, ws, user_id)

    # I'm online!
    r.set(ol_key, 1)
    r.expire(ol_key, 60)

    # Tell other listeners that you are listening
    r.hset(plls_key, user_id, '%s:%s' % (user['name'], user['username']))
    r.publish(plrt_key, '%s:pl_listen:%s' % (user_id, json.dumps(user)))

    # Who's listening?
    listeners = []
    for ls_id, ls in r.hgetall(plls_key).items():
      if ls_id != user_id:
        ls_ol_key = 'ol:%s' % ls_id
        if r.get(ls_ol_key):
          ls_name, ls_username = ls.split(':', 1)
          listeners.append({
            'id': ls_id,
            'name': ls_name,
            'username': None if ls_username == 'None' else ls_username,
          })
        else:
          r.hdel(plls_key, ls_id)
    ws.send('pl_listeners:%s' % json.dumps(listeners))

    try:
      while True:
        message = ws.receive()
        if message:
          # I'm still online!
          if message == 'ol':
            r.expire(ol_key, 60)
        else:
          break

    finally:
      # Say bye bye
      r.hdel(plls_key, user['id'])
      r.publish(plrt_key, '%s:pl_leave:%s' % (user_id, json.dumps(user)))

      publisher.kill()

  return 'ok'


class GeventResponse(object):
  status = None
  headers = None
  response_length = None

  def __init__(self, status, headers, clength):
    self.status = status
    self.headers = headers
    self.response_length = clength


class WSGIHandler(WebSocketHandler):

  def log_request(self):
    if not self.environ.get('wsgi.websocket'):
      start = datetime.fromtimestamp(self.time_start)
      finish = datetime.fromtimestamp(self.time_finish)
      response_time = finish - start
      resp = GeventResponse(self.status, self.response_headers, self.response_length)
      req_headers = [h.split(":", 1) for h in self.headers.headers]
      self.server.log.access(resp, req_headers, self.environ, response_time)

  def get_environ(self):
    env = super(WSGIHandler, self).get_environ()
    env['gunicorn.sock'] = self.socket
    env['RAW_URI'] = self.path
    return env


class GeventWebSocketWorker(GeventPyWSGIWorker):
  wsgi_handler = WSGIHandler

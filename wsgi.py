from ytdj import YTDJ
import cherrypy


application = cherrypy.Application(YTDJ())

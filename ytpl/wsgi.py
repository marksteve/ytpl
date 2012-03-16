from ytdj import YTDJ
import cherrypy


appplication = cherrypy.Application(YTDJ())

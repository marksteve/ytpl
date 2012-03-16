from ytdj import YTDJ
import cherrypy


application = cherrypy.tree.mount(YTDJ())

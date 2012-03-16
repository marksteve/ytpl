from ytpl import YTPL
import cherrypy


application = cherrypy.tree.mount(YTPL())

from ytpl import YTPL, setup_server
import cherrypy

setup_server()
application = cherrypy.tree.mount(YTPL())

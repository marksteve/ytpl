from setuptools import setup


setup(
  name='ytpl',
  version='0.0.1',
  packages=['ytpl'],
  author='Mark Steve Samson',
  author_email='contact@marksteve.me',
  description='Youtube Playlists',
  entry_points={
    'console_scripts': ['ytpl = ytpl:start'],
  },
  install_requires=[
    'cherrypy',
    'redis',
    'mako',
    'requests',
    'gdata==2.0.16',
  ],
)

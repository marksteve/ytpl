from setuptools import setup


setup(
  name='ytpl',
  version='0.0.1',
  py_modules=['ytpl'],
  author='Mark Steve Samson',
  author_email='contact@marksteve.me',
  description='Youtube Playlists',
  entry_points={
    'console_scripts': ['ytpl = ytpl:start'],
  },
  dependency_links=[
    'https://github.com/marksteve/python-foauth2/tarball/patch-1#egg=foauth2',
  ],
  install_requires=[
    'cherrypy',
    'redis',
    'mako',
    'requests',
    'fboauth2',
  ],
)

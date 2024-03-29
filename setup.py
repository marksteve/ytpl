from setuptools import setup


setup(
  name='ytpl',
  version='0.1.0',
  py_modules=['ytpl'],
  author='Mark Steve Samson',
  author_email='contact@marksteve.me',
  description='Youtube Playlists',
  dependency_links=[
    'https://github.com/marksteve/fboauth2/tarball/master#egg=fboauth2-0.0.2',
  ],
  install_requires=[
    'flask',
    'fboauth2==0.0.2',
    'hiredis',
    'mako',
    'redis',
    'requests',
    'gevent-websocket',
    'gunicorn',
  ],
)

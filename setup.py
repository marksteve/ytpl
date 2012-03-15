from setuptools import setup


setup(
  name='ytdj',
  version='0.0.1',
  packages=['ytdj'],
  scripts={},
  author='Mark Steve Samson',
  author_email='contact@marksteve.me',
  description='Youtube DJ',
  entry_points={
    'console_scripts': ['ytdj = ytdj:start'],
  },
  install_requires=[
    'cherrypy',
    'slumber',
    'redis',
    'mako',
    'requests'
  ],
)

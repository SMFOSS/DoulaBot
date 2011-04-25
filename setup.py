from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='DoulaBot',
      version=version,
      description="A simple irc bot for communicating about release and deployment events and allowing irc participant to queue release and deployment tasks.",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='irc doula release deployment queue',
      author='D. Whit Morriss',
      author_email='whit at surveymonkey.com',
      url='http://code.surveymonkey.com',
      license='MIT',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )

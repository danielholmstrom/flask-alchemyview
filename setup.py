"""
Flask-Alchemyview
~~~~~~~~~~~~~~~~~

A Flask ModelView for SQLAlchemy models.

"""

import os
from setuptools import find_packages
from distutils.core import setup

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()

# Requirements for the package
install_requires = [
    'SQLAlchemy>=0.8.0',
    'Flask-Classy',
    'colander',
    'sphinx'
]

# Requirement for running tests
test_requires = install_requires + [
    'dictalchemy',
    'flask-sqlalchemy'
]

setup(name='Flask-AlchemyView',
      version='0.1.2',
      description="Simple ModelView for auto-generating Flask Views based on "
      "SQLAlchemy models",
      long_description=README,
      url='http://github.com/danielholmstrom/flask-alchemyview/',
      license='MIT',
      author='Daniel Holmstrom',
      author_email='holmstrom.daniel@gmail.com',
      platforms='any',
      classifiers=['Development Status :: 5 - Production/Stable',
                   'License :: OSI Approved :: MIT License',
                   'Environment :: Web Environment',
                   'Intended Audience :: Developers',
                   'Operating System :: OS Independent',
                   'Programming Language :: Python',
                   'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
                   'Topic :: Software Development :: '
                   'Libraries :: Python Modules'],
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      tests_require=test_requires,
      test_suite='tests',
      )

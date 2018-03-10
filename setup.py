import io
import os

from setuptools import setup

NAME = 'pinub'
REQUIRES_PYTHON = '>=3.6.0'
REQUIRES = [
    'flask', 'psycopg2-binary', 'bcrypt', 'gunicorn'
]

here = os.path.abspath(os.path.dirname(__file__))

with io.open(os.path.join(here, 'LICENSE'), encoding='utf-8') as f:
    licence = '\n' + f.read()

setup(
    name=NAME,
    author='Danilo Braband',
    url='https://github.com/dabio/pinub',
    py_modules=['pinub'],
    python_requires=REQUIRES_PYTHON,
    include_package_data=True,
    install_requires=REQUIRES,
    license=license
)

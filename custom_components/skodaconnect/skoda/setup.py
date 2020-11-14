from setuptools import setup

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='skoda',
    description='Communicate with Skoda Connect',
    author='n/a',
    author_email='n/a@mama.sk',
    url='na',
    long_description=long_description,
    long_description_content_type='text/markdown',
    py_modules=[
        "skoda",
        "dashboard",
        "utilities",
        "__init__"
    ],
    provides=["skoda"],
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    use_scm_version=True,
    setup_requires=[
        'setuptools_scm',
        'pytest>=5,<6',
    ]
)

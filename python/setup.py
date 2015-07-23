#! /usr/bin/env python
from setuptools import setup, Extension, Command


class PyTest(Command):
    description = "run py.test unit tests"
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        import sys,subprocess
        errno = subprocess.call([sys.executable, 'runtests.py'])
        raise SystemExit(errno)




camlmodule = Extension(
    "caml",
    sources=["bincat.c"],
    libraries=["ml"],
    library_dirs=["../ocaml/src"])

setup(
    cmdclass = {'test': PyTest},
    name             = 'BinCAT',
    version          = '0.1',
    author           = 'Sarah Zennou',
    author_email     = 'sarah.zennou@airbus.com',
    description      = 'BINnary Code Aanalysis Toolkit',
    long_description = open('README.txt').read(),
    packages         = ['bincat'],
    license          = 'GPLv2'
)
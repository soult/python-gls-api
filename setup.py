#!/usr/bin/env python

from distutils.core import setup

setup(
    name="python-gls-api",
    version="0.1.0a7",
    description="Python3 library for interacting with the GLS website as a registered customer",
    long_description="A Python3 library for interacting with the GLS (General Logistic Systems) Group website. It supports creating new shipments and inspecting existing shipments. NB: This is not a shipment tracking library - it requires an account with GLS.",
    author="David Triendl",
    author_email="david@triendl.name",
    packages=["glsapi"],
    install_requires=["requests>=2.0.0"],
)

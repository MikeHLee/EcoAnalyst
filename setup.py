#!/usr/bin/env python3
"""
EcoAnalyst - Setup Configuration

A library for understanding ecosystems, economies, and abstract 
physically interacting networks through graph-based modeling.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="ecoanalyst",
    version="2.0.0",
    author="Mike Lee",
    author_email="",
    description="A library for modeling and analyzing mass, energy, and information flows in ecosystems, economies, and physically interacting networks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MikeHLee/ecoanalyst",
    project_urls={
        "Bug Tracker": "https://github.com/MikeHLee/ecoanalyst/issues",
        "Documentation": "https://github.com/MikeHLee/ecoanalyst#readme",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "networkx>=3.2",
        "numpy>=1.26.0",
        "pandas>=2.0.0",
        "scipy>=1.10.0",
        "matplotlib>=3.7.0",
        "pydantic>=2.6.0",
    ],
    extras_require={
        "api": [
            "fastapi>=0.110.0",
            "uvicorn>=0.27.0",
            "httpx>=0.26.0",
        ],
        "ml": [
            "scikit-learn>=1.3.0",
            "pymc>=5.7.0",
        ],
        "mcp": [
            "mcp>=0.9.0",
        ],
        "viz": [
            "seaborn>=0.12.0",
            "plotly>=5.18.0",
        ],
        "db": [
            "psycopg2-binary>=2.9.9",
        ],
        "full": [
            "fastapi>=0.110.0",
            "uvicorn>=0.27.0",
            "httpx>=0.26.0",
            "scikit-learn>=1.3.0",
            "pymc>=5.7.0",
            "mcp>=0.9.0",
            "seaborn>=0.12.0",
            "plotly>=5.18.0",
            "psycopg2-binary>=2.9.9",
        ],
    },
    entry_points={
        "console_scripts": [
            "ecoanalyst=ecoanalyst.cli:main",
        ],
    },
)

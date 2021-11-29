import pathlib

import pkg_resources
import setuptools

from version import __version__

with pathlib.Path('pip-requirements.txt').open() as requirements_txt:
    install_requires = [
        str(requirement)
        for requirement
        in pkg_resources.parse_requirements(requirements_txt)
    ]

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='apollogize',
    version=__version__,
    author='Zac Chien',
    author_email='fengying0709@gmail.com',
    url='https://github.com/zacfeng/Apollogize',
    description='Apollogize is a command line tool which assists the employers who forgot to check-in and check-out in Apollo app.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    install_requires=install_requires,
    license='GPLv3',
    entry_points={
        'console_scripts': [
            'apollogize=apollogize.apollogize:entry',
        ]
    },
)

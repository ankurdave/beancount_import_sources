from os import path
from setuptools import find_packages, setup

with open(path.join(path.dirname(__file__), 'README.md')) as readme:
    LONG_DESCRIPTION = readme.read()

setup(
    name='beancount_import_sources',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    description='A collection of sources for beancount-import',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    url='https://github.com/ankurdave/beancount_import_sources',
    author='Ankur Dave',
    author_email='ankurdave@gmail.com',
    license='BSD',
    keywords='plugins double-entry banking beancount accounting',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'beancount-import',
    ],
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Financial and Insurance Industry',
        'Natural Language :: English',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Office/Business :: Financial :: Accounting',
        'Topic :: Office/Business :: Financial :: Investment',
    ],
)

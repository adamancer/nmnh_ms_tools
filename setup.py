from setuptools import setup, find_packages

# Read long_description from file
try:
    long_description = open('README.rst', 'r').read()
except FileNotFoundError:
    long_description = ('Please see'
                        ' https://github.com/adamancer/nmnh_ms_tools.git'
                        ' for more information about the nmnh_ms_tools'
                        ' package.')

setup(name='nmnh_ms_tools',
      version='0.1',
      description=("Tools for working with natural history collections data"
                   " used in the Department of Mineral Sciences at the"
                   " Smithsonian's National Museum of Natural History"),
      long_description=long_description,
      classifiers = [
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
      ],
      url='https://github.com/adamancer/nmnh_ms_tools.git',
      author='adamancer',
      author_email='mansura@si.edu',
      license='MIT',
      packages=find_packages(),
      install_requires=[
        'beautifulsoup4',
        'bibtexparser',
        'geographiclib',
        'html5lib',
        'inflect',
        'lxml',
        'matplotlib',
        'nameparser',
        'nltk',
        'numpy',
        'Pillow',
        'pyproj',
        'pytest',
        'pytz',
        'PyYAML',
        'requests',
        'requests_cache',
        'Shapely',
        'six',
        'SQLAlchemy',
        'titlecase',
        'Unidecode',
      ],
      include_package_data=True,
      zip_safe=False)

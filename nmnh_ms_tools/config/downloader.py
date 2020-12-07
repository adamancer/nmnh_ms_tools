"""Downloads data files not included in the GitHib repo

Files downloaded to _files/data/downloads include:
+ georef_data.sqlite (used for georeferencing)
+ geotree.json (used for classifying geological specimens)
+ nmnh_taxonomy.json (used to assign topics to snippets)

"""
import hashlib
import os
import tempfile
import zipfile

import requests

from .config import DATA_DIR




HASHES = {
    'https://windingway.org/files/nmnh_ms_tools_20201207.zip': '639f0bc4688800571a455f19f44e81d5'
}


def download(url=None):
    """Downloads untracked data files"""
    print('FIRST TIME SETUP: Downloading required data files...')
    if url is None:
        url = list(HASHES.keys())[-1]

    response = requests.get(url)
    if response.status_code == 200:

        # Verify file against hash
        if hashlib.md5(response.content).hexdigest() != HASHES[url]:
            raise IOError('Hash incorrect')

        # Write content to a temporary file to use with zipfile
        temp = tempfile.NamedTemporaryFile()
        temp.write(response.content)
        temp.seek(0)

        # Set and verify output directory
        output_dir = os.path.join(DATA_DIR, 'downloads')
        try:
            os.mkdir(output_dir)
        except OSError:
            pass

        # Extract files to download directory
        with zipfile.ZipFile(temp) as f:
            for member in f.namelist():
                try:
                    open(os.path.join(output_dir, member))
                except FileNotFoundError:
                    f.extract(member, output_dir)




if not os.path.exists(os.path.join(DATA_DIR, 'downloads')):
    download_missing()

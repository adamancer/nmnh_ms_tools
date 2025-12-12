"""Downloads data files not included in the GitHib repo

Files downloaded to _files/data/downloads include:
+ geohelper.sqlite (used for georeferencing)
+ geotree.json (used for classifying geological specimens)
+ nmnh_taxonomy.json (used to assign topics to snippets)

"""

import logging
import hashlib
import os
import tempfile
import zipfile

import requests

from .config import DATA_DIR


logger = logging.getLogger(__name__)


HASHES = {
    "https://windingway.org/files/nmnh_ms_tools_20201207.zip": "f74b9721c13e1d1f31c01ba577392ce0914e4639988d86df4a0ff1b578911e79"
}


def download(url=None, sha256hash=None):
    """Downloads data files that are not included in the repo

    Parameters
    ----------
    url : str
        url of download
    sha256hash : str
        expected hash of file content
    """
    if url is None:
        for url in HASHES:
            download(url)
    else:
        print(f"Downloading {url}")
        response = requests.get(url)
        if response.status_code == 200:

            # Verify file against hash
            resphash = hashlib.sha256(response.content).hexdigest()
            if sha256hash is None:
                sha256hash = HASHES[url]
            if resphash != sha256hash:
                raise IOError(f"Hash incorrect: {sha256hash}")

            # Write content to a temporary file to use with zipfile
            temp = tempfile.NamedTemporaryFile()
            temp.write(response.content)
            temp.seek(0)

            # Set and verify output directory
            output_dir = os.path.join(DATA_DIR, "downloads")
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
                        print(f" Added {member} to {output_dir}")
                        f.extract(member, output_dir)

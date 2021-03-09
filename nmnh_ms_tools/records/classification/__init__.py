"""Constructs a hierarchy of rock and mineral names"""
from .taxon import Taxon
from .taxalist import TaxaList
from .taxanamer import TaxaNamer
from .taxaparser import TaxaParser
from ...config import DATA_DIR
from ...utils import is_different



def get_tree(src=None):
    """Retrieves the taxonomic tree, updating from src if given"""
    import os
    import shutil
    try:
        from minsci.xmu.tools.etaxonomy import TaXMu
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            'get_tree requires the minsci module (https://github.com/adamancer/minsci)'
        )

    json_path = os.path.join(DATA_DIR, 'downloads', 'geotree.json')
    if src is None:
        taxmu = TaXMu(json_path)
    else:
        # Verify that source format is the right type
        ext = os.path.splitext(src)[-1].lower()
        if ext not in ('.json', '.xml'):
            raise IOError('Invalid file extension')

        # Rebuild tree if src is different from the current JSON file
        if is_different(src, json_path):
            taxmu = TaXMu(src)
            shutil.copy2(os.path.splitext(src) + '.json', json_path)
            if not taxmu.check():
                raise ValueError('Incongruities found in hierarchy! Please'
                                 ' import update_{timestamp}.xml into EMu'
                                 ' and re-export')

    taxmu.tree.timestamp = taxmu.modified
    TaxaParser.tree = taxmu.tree
    return taxmu.tree

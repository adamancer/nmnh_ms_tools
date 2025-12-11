import json
import os
from datetime import datetime
from functools import cache

from xmu import EMuReader, EMuRecord, write_import

from .taxon import Taxon
from .taxaparser import TaxaParser
from .taxatree import TaxaTree, NameIndex, StemIndex
from ...config import CONFIG


@cache
def get_tree(src: str = None):
    """Builds a taxonomic tree for geological specimens

    Parameters
    ----------
    src : str
        path to EMu export

    Returns
    -------
    TaxaTree
        taxonomic tree
    """

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    tree = TaxaTree()

    # Add tree to taxa classes
    Taxon.tree = tree
    TaxaParser.tree = tree

    # Disable index for the duration of the build
    tree.disable_index = True

    json_path = CONFIG["data"]["taxa_tree"]

    if not src:
        with open(json_path, encoding="utf-8") as f:
            tree.update({k: Taxon(v) for k, v in json.load(f).items()})
    else:

        # Remove indexes
        for idx in tree.indexers.values():
            try:
                os.remove(idx.path)
            except OSError:
                pass
            else:
                print(f"Removed {idx.path}")

        updates = []
        errors = []

        reader = EMuReader(src, json_path=os.path.splitext(src)[0] + ".json")
        for rec in reader:
            reader.report_progress()
            try:
                rec = Taxon(EMuRecord(rec, module=reader.module))
                tree[rec["irn"]] = rec
            except:
                errors.append((rec["irn"], "Read failed"))

        tree.disable_index = False

        # Create indexes
        NameIndex(tree)
        StemIndex(tree)

        # Populate relationships
        tree._assign_synonyms()
        tree._assign_similar()
        tree._assign_official()

        # Check current designation
        for key, taxon in tree.items():
            if key.isnumeric():
                try:
                    rec = taxon.fix_current()
                    if rec:
                        updates.append(EMuRecord(rec, module=reader.module))
                except (AttributeError, KeyError):
                    errors.append((key, "taxon.fix_current() failed"))

        # Check for other integrity issues
        for key, taxon in tree.items():
            if key.isnumeric():
                try:
                    rec = taxon.fix()
                    if rec:
                        updates.append(EMuRecord(rec, module=reader.module))
                except (KeyError, ValueError) as err:
                    errors.append((key, "taxon.fix() failed"))

        # Create import file with updates that can be made automatically
        if updates:
            write_import(updates, f"update_{timestamp}.xml")

        # Test relationships if no other errors found
        if not errors:
            for key, taxon in tree.items():
                if key.isnumeric():
                    try:
                        taxon.preferred()
                        taxon.parents()
                        taxon.official()
                    except:
                        errors.append((key, "Relationship check failed"))

        # List errors if any found
        if errors:
            raise ValueError(f"Could not generate tree: {errors}")

        tree.to_json(json_path)

    tree.disable_index = False

    return tree

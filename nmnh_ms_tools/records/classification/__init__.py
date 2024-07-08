"""Constructs a hierarchy of rock and mineral names"""

from functools import cache

from .taxon import Taxon
from .taxalist import TaxaList
from .taxanamer import TaxaNamer
from .taxaparser import TaxaParser
from ...config import CONFIG
from ...utils import is_different


@cache
def get_tree(src=None):

    import json
    import os
    from datetime import datetime
    from xmu import EMuReader, EMuRecord, write_import

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    tree = TaxaNamer()
    Taxon.tree = tree
    TaxaParser.tree = tree

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
            write_import(updates, "update_{}.xml".format(timestamp))

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

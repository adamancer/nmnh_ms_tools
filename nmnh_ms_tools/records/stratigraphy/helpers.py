"""Defines constants and functions used in the stratigraphy submodule"""
import copy
import re

import numpy as np
from titlecase import titlecase

from ..core import Record
from ...bots.adamancer import AdamancerBot
from ...bots.macrostrat import MacrostratBot
from ...utils import std_case




CHRONOSTRAT_LEVELS = [
    'eonothem',
    'erathem',
    'system',
    'series',
    'stage',
    'substage'
]

LITHOSTRAT_LEVELS = {
    'gp': 'group',
    'fm': 'formation',
    'mbr': 'member',
    #'bd': 'bed'
}

LITHOLOGIES = {
    'cgl': 'conglomerate',
    'dol': 'dolomite',
    'ls': 'limestone',
    'sh': 'shale',
    'sl': 'slate',
    'ss': 'sandstone',
    'volc': 'volcanic',
}

for lithology in [
    'anhydrite',
    'basalt',
    'calcareous',
    'carbonate',
    'chalk',
    'clay',
    'claystone',
    'dolomite',
    'gneiss',
    'granite',
    'iron formation',
    'marl',
    'mudstone',
    'oolite',
    'sand',
    'siltstone'
]:
    LITHOLOGIES[lithology] = lithology


MODIFIERS = [
    'base',
    'lower',
    'middle',
    'mid',
    'upper',
    'top',
    'early',
    'late'
]




def std(name):
    """Standardizes a stratigraphic name"""
    words = {
        'cr': 'creek',
        'mt': 'mount',
        'mtn': 'mountain',
        'r': 'river'
    }
    for find, repl in words.items():
        pattern = r'\b{}(\.|\b)'.format(find.capitalize())
        name = re.sub(pattern, repl.capitalize(), name)
    return name


def long_name(name):
    """Returns the long form of the unit name"""
    name = std(name)
    for find, repl in LITHOSTRAT_LEVELS.items():
        pattern = r'\b({})(?=\b|\.)'.format(find)
        name = re.sub(pattern, repl, name, flags=re.I)
    for find, repl in LITHOLOGIES.items():
        pattern = r'\b({})\b'.format(find)
        name = re.sub(pattern, repl, name, flags=re.I)
    return titlecase(name)


def short_name(name):
    """Returns the short form of the unit name"""
    name = std(name)
    for repl, find in LITHOSTRAT_LEVELS.items():
        name = re.sub(r'\b({})\b'.format(find), repl, name, flags=re.I)
    for repl, find in LITHOLOGIES.items():
        name = re.sub(r'\b({})\b'.format(find), repl, name, flags=re.I)
    # Fix combinations (e.g., Emily Iron Formation Member)
    pattern = r'({0}) ({0})'.format('|'.join(LITHOSTRAT_LEVELS.keys()))
    match = re.search(pattern, name)
    if match is not None:
        name = name.replace(match.group(1), LITHOSTRAT_LEVELS[match.group(1)])
    return titlecase(name)


def std_modifiers(unit, use_age=False):
    """Standardizes unit names to upper/lower instead of late/early"""
    if unit:
        modifiers = {
            'early': 'lower',
            'early/lower': 'lower',
            'lower/early': 'lower',
            'late': 'upper',
            'late/upper': 'upper',
            'upper/late': 'upper',
            'mid': 'middle'
        }
        if use_age:
            for key, val in modifiers.items():
                modifiers[key] = 'early' if val == 'lower' else 'late'
        std = unit
        for key in sorted(modifiers, key=len, reverse=True):
            val = modifiers[key]
            pattern = r'\b{}\b'.format(key)
            match = re.search(pattern, std, flags=re.I)
            if match is not None:
                repl = std_case(val, match.group(0))
                std = re.sub(pattern, repl, std, flags=re.I)
        return std
    return unit


def base_name(unit):
    """Returns the unmodified name from a stratigraphic unit"""
    pattern = r'\b{}\b'.format('|'.join(MODIFIERS))
    return re.sub(pattern, '', unit, flags=re.I).replace('()', '').strip(' -')

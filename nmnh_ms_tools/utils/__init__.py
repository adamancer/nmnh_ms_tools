"""Defines (mostly) standalone functions and classes"""

from .. import _ImportClock

with _ImportClock("utils"):
    from .classes import repr_class, str_class
    from .clock import Clocker, clock, clock_all_methods, clock_snippet, report
    from .coords import (
        Coordinate,
        Latitude,
        Longitude,
        estimate_uncertainty,
        parse_coordinate,
        round_to_uncertainty,
    )
    from .dicts import (
        AbbrDict,
        AttrDict,
        BaseDict,
        IndexedDict,
        NamedDict,
        StaticDict,
        combine,
        dictify,
        get_all,
        get_common_items,
        get_first,
        prune,
    )
    from .emu import (
        create_note,
        create_markdown_note,
        create_yaml_note,
    )
    from .files import (
        HashCheck,
        copy_if,
        fast_hash,
        hash_file,
        hash_file_if_exists,
        hash_image_data,
        hasher,
        get_mtime,
        is_different,
        is_newer,
        is_older,
        load_dict,
        skip_hashed,
    )
    from .geo import (
        am_longitudes,
        azimuth_uncertainty,
        bounding_box,
        continuous,
        crosses_180,
        draw_circle,
        draw_polygon,
        encircle,
        enhull,
        epsg_id,
        fix_shape,
        get_azimuth,
        get_dist_km,
        normalize_shape,
        pm_longitudes,
        similar,
        slope,
        subhorizontal,
        subvertical,
        translate,
        translate_with_uncertainty,
        trim,
    )
    from .lists import (
        as_list,
        as_set,
        as_tuple,
        dedupe,
        iterable,
        most_common,
        oxford_comma,
    )
    from .misc import (
        ABCEncoder,
        clear_empty,
        coerce,
        configure_log,
        get_ocean_name,
        localize_datetime,
        normalize_sample_id,
        prompt,
        read_dwc_archive,
        validate_direction,
        write_emu_search,
    )
    from .measurements import parse_measurement, parse_measurements
    from .numeric import as_numeric, base_to_int, int_to_base, frange, num_dec_places
    from .prefixed_num import PrefixedNum
    from .preps import Preparation
    from .standardizers import (
        LocStandardizer,
        Standardizer,
        std_names,
        std_identifier,
    )
    from .strings import (
        add_article,
        as_str,
        is_uncertain,
        collapse_whitespace,
        lcfirst,
        natsortable,
        overlaps,
        plural,
        same_to_length,
        singular,
        slugify,
        std_case,
        to_attribute,
        to_camel,
        to_dwc_camel,
        to_pascal,
        to_digit,
        to_pattern,
        truncate,
        ucfirst,
    )

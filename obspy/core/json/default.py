# -*- coding: utf-8 -*-
"""
JSON Encoder default function

This module provides:
---------------------
Default : a class to create a "default" function accepted by the
python json module Encoder classes, valid for obspy.core.event objects

Example
-------
>>> import json
>>> from obspy import readEvents
>>> from obspy.core.json import Default
>>> c = readEvents()
>>> d = Default(omit_nulls=False)
>>> s = json.dumps(c, default=d)

"""
from obspy.core.event import (AttribDict, Catalog, UTCDateTime,
                              ResourceIdentifier)


class Default(object):
    """
    Class to create a "default" function for the json.dump* functions
    which is passed to the JSONEncoder.

    """
    _catalog_attrib = ('events', 'comments', 'description', 'creation_info',
                       'resource_id')

    OMIT_NULLS = None
    TIME_FORMAT = None

    def __init__(self, omit_nulls=True, time_format=None):
        """
        Create a "default" function for JSONEncoder for ObsPy objects

        :param bool omit_nulls: Leave out any null or empty values (True)
        :param str time_format: Format string passed to strftime (None)

        """
        # Allows customization of the function
        self.OMIT_NULLS = omit_nulls
        self.TIME_FORMAT = time_format

    def __call__(self, obj):
        """
        Deal with obspy event objects in JSON Encoder

        This function can be passed to the json module's
        'default' keyword parameter

        """
        # Most event objects have dict methods, construct a dict
        # and deal with special cases that don't
        if isinstance(obj, AttribDict):
            # Map to a serializable dict
            # Leave out nulls, empty strings, list, dicts, except for numbers
            if self.OMIT_NULLS:
                return {k: v for k, v in obj.iteritems() if v or v == 0}
            else:
                return {k: v for k, v in obj.iteritems()}
        elif isinstance(obj, Catalog):
            # Catalog isn't a dict
            return {k: getattr(obj, k) for k in self._catalog_attrib
                    if getattr(obj, k)
                    }
        elif isinstance(obj, UTCDateTime):
            if self.TIME_FORMAT is None:
                return str(obj)
            else:
                return obj.strftime(self.TIME_FORMAT)
        elif isinstance(obj, ResourceIdentifier):
            # Always want ID as a string
            return str(obj)
        else:
            return None

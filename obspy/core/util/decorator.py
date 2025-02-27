# -*- coding: utf-8 -*-
"""
Decorator used in ObsPy.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
import functools
import inspect
from pathlib import Path
import re
import socket
import tarfile
import warnings
import zipfile

import numpy as np
import pytest
from decorator import decorator

from obspy.core.util import get_example_file
from obspy.core.util.base import NamedTemporaryFile
from obspy.core.util.deprecation_helpers import ObsPyDeprecationWarning


def deprecated(warning_msg=None):
    """
    This is a decorator which can be used to mark functions as deprecated.

    .. note::
        Actually, this is not a decorator itself but a decorator factory,
        returning the correct decorator for the specified options. It can be
        used just like a decorator.

    It will result in a warning being emitted when the function is used.
    """
    @decorator
    def _deprecated(func, *args, **kwargs):
        if 'deprecated' in str(func.__doc__).lower():
            msg = func.__doc__
        elif warning_msg:
            msg = warning_msg
            func.__doc__ = warning_msg
        else:
            msg = "Call to deprecated function %s." % func.__name__
        warnings.warn(msg, category=ObsPyDeprecationWarning, stacklevel=3)
        return func(*args, **kwargs)
    return _deprecated


def deprecated_keywords(keywords):
    """
    Decorator for marking keywords as deprecated.

    .. note::
        Actually, this is not a decorator itself but a decorator factory,
        returning the correct decorator for the specified options. It can be
        used just like a decorator.

    :type keywords: dict
    :param keywords: old/new keyword names as key/value pairs.
    """
    def fdec(func):
        fname = func.__name__
        msg = "Deprecated keyword %s in %s() call - please use %s instead."
        msg2 = "Deprecated keyword %s in %s() call - ignoring."
        msg3 = ("Conflicting deprecated keywords (%s) in %s() call"
                " - please use new '%s' keyword instead.")

        @functools.wraps(func)
        def echo_func(*args, **kwargs):
            # check if multiple deprecated keywords get mapped to the same new
            # keyword
            new_keyword_appearance_counts = dict.fromkeys(keywords.values(), 0)
            for key, new_key in keywords.items():
                if key in kwargs:
                    new_keyword_appearance_counts[new_key] += 1
            for key_ in keywords.values():
                # ignore `None` as new value, it means that no mapping is
                # happening..
                if key_ is None:
                    continue
                if new_keyword_appearance_counts[key_] > 1:
                    conflicting_keys = ", ".join(
                        [old_key for old_key, new_key in keywords.items()
                         if new_key == key_])
                    raise Exception(msg3 % (conflicting_keys, fname, new_key))
            # map deprecated keywords to new keywords
            for kw in list(kwargs):
                if kw in keywords:
                    nkw = keywords[kw]
                    if nkw is None:
                        warnings.warn(msg2 % (kw, fname),
                                      category=ObsPyDeprecationWarning,
                                      stacklevel=3)
                    else:
                        warnings.warn(msg % (kw, fname, nkw),
                                      category=ObsPyDeprecationWarning,
                                      stacklevel=3)
                        kwargs[nkw] = kwargs[kw]
                    del kwargs[kw]
            return func(*args, **kwargs)
        return echo_func

    return fdec


@decorator
def skip_on_network_error(func, *args, **kwargs):
    """
    Decorator to mark test routines that fail with certain network
    errors (e.g. timeouts) as "skipped" rather than "Error".
    """
    try:
        return func(*args, **kwargs)
    ###################################################
    # add more except clauses like this to add other
    # network errors that should be skipped
    except socket.timeout as e:
        if str(e) == "timed out":
            pytest.skip(str(e))
    ###################################################
    except socket.error as e:
        if str(e) == "[Errno 110] Connection timed out":
            pytest.skip(str(e))
    # general except to be able to generally reraise
    except Exception:
        raise


@decorator
def uncompress_file(func, filename, *args, **kwargs):
    """
    Decorator used for temporary uncompressing file if .gz or .bz2 archive.
    """
    if not kwargs.pop('check_compression', True):
        return func(filename, *args, **kwargs)
    if not isinstance(filename, str):
        return func(filename, *args, **kwargs)
    elif not Path(filename).exists():
        msg = "File not found '%s'" % (filename)
        raise IOError(msg)
    # check if we got a compressed file or archive
    obj_list = []
    if tarfile.is_tarfile(filename):
        try:
            # reading with transparent compression
            with tarfile.open(filename, 'r|*') as tar:
                for tarinfo in tar:
                    # only handle regular files
                    if not tarinfo.isfile():
                        continue
                    data = tar.extractfile(tarinfo).read()
                    # Skip empty files - we don't need them no matter what
                    # and it guards against rare cases where waveforms files
                    # are also slightly valid tar-files.
                    if not data:
                        continue
                    obj_list.append(data)
        except Exception:
            pass
    elif zipfile.is_zipfile(filename):
        try:
            with zipfile.ZipFile(filename) as zip:
                if b'obspy_no_uncompress' in zip.comment:
                    # be nice to plugins based on zip format
                    # do not uncompress the file if tag is present
                    # see issue #3192
                    obj_list = None
                else:
                    obj_list = [zip.read(name) for name in zip.namelist()]
        except Exception:
            pass
    elif filename.endswith('.bz2'):
        # bz2 module
        try:
            import bz2
            with open(filename, 'rb') as fp:
                obj_list.append(bz2.decompress(fp.read()))
        except Exception:
            pass
    elif filename.endswith('.gz'):
        # gzip module
        try:
            import gzip
            with gzip.open(filename, 'rb') as fp:
                obj_list.append(fp.read())
        except Exception:
            pass
    # handle results
    if obj_list:
        # write results to temporary files
        result = None
        for obj in obj_list:
            with NamedTemporaryFile() as tempfile:
                tempfile._fileobj.write(obj)
                stream = func(tempfile.name, *args, **kwargs)
                # just add other stream objects to first stream
                if result is None:
                    result = stream
                else:
                    result += stream
    else:
        # no compressions
        result = func(filename, *args, **kwargs)
    return result


@decorator
def raise_if_masked(func, *args, **kwargs):
    """
    Raises if the first argument (self in case of methods) is a Trace with
    masked values or a Stream containing a Trace with masked values.
    """
    arrays = []
    # first arg seems to be a Stream
    if hasattr(args[0], "traces"):
        arrays = [tr.data for tr in args[0]]
    # first arg seems to be a Trace
    if hasattr(args[0], "data") and isinstance(args[0].data, np.ndarray):
        arrays = [args[0].data]
    for arr in arrays:
        if np.ma.is_masked(arr):
            msg = "Trace with masked values found. This is not " + \
                  "supported for this operation. Try the split() " + \
                  "method on Trace/Stream to produce a Stream with " + \
                  "unmasked Traces."
            raise NotImplementedError(msg)
    return func(*args, **kwargs)


@decorator
def skip_if_no_data(func, *args, **kwargs):
    """
    Does nothing if the first argument (self in case of methods) is a Trace
    with no data in it.
    """
    if not args[0]:
        return
    return func(*args, **kwargs)


def map_example_filename(arg_kwarg_name):
    """
    Decorator that replaces "/path/to/filename" patterns in the arg or kwarg
    of the specified name with the correct file path. If the pattern is not
    encountered nothing is done.

    .. note::
        Actually, this is not a decorator itself but a decorator factory,
        returning the correct decorator for the specified options. It can be
        used just like a decorator.

    :type arg_kwarg_name: str
    :param arg_kwarg_name: name of the arg/kwarg that should be (tried) to map
    """
    @decorator
    def _map_example_filename(func, *args, **kwargs):
        prefix = '/path/to/'
        # check kwargs
        if arg_kwarg_name in kwargs:
            if isinstance(kwargs[arg_kwarg_name], str):
                if re.match(prefix, kwargs[arg_kwarg_name]):
                    try:
                        kwargs[arg_kwarg_name] = \
                            get_example_file(kwargs[arg_kwarg_name][9:])
                    # file not found by get_example_file:
                    except IOError:
                        pass
        # check args
        else:
            try:
                inspected_args = [
                    p.name
                    for p in inspect.signature(func).parameters.values()
                ]
            except AttributeError:
                inspected_args = inspect.getargspec(func).args
            try:
                ind = inspected_args.index(arg_kwarg_name)
            except ValueError:
                pass
            else:
                if ind < len(args) and isinstance(args[ind], str):
                    # need to check length of args from inspect
                    if re.match(prefix, args[ind]):
                        try:
                            args = list(args)
                            args[ind] = get_example_file(args[ind][9:])
                            args = tuple(args)
                        # file not found by get_example_file:
                        except IOError:
                            pass
        return func(*args, **kwargs)
    return _map_example_filename


if __name__ == '__main__':
    import doctest
    doctest.testmod(exclude_empty=True)

"""Defines simple class to track durations of function calls"""
import csv
import datetime as dt
import inspect
import pprint as pp
from collections import namedtuple
from functools import wraps




CLOCKED = {}
Call = namedtuple('Call', ['function', 'args', 'kwargs', 'start', 'end'])
Result = namedtuple('Result', ['function', 'count', 'total', 'mean', 'max'])




class Clocker:
    """Defines the context manager used to clock snippets"""

    def __init__(self, name):
        self.name = name
        self.start = None


    def __enter__(self):
        self.start = dt.datetime.now()


    def __exit__(self, exc_type, exc_val, exc_tb):
        update_results(Call(self.name, [], {}, self.start, dt.datetime.now()))




def clock(func):
    """Clocks the decorated function"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = dt.datetime.now()
        result = func(*args, **kwargs)
        end_time = dt.datetime.now()
        # Store result
        func_path = '.'.join([func.__module__, func.__qualname__])
        update_results(Call(func_path, [], {}, start_time, end_time))
        return result
    return wrapper


def clock_snippet(name):
    """Sets up a context manager to clock a snippet"""
    return Clocker(name)


def update_results(call):
    """Updates results for clocked function"""
    duration = (call.end - call.start).total_seconds()
    try:
        results = CLOCKED[call.function]
        results['count'] += 1
        results['total'] += duration
        if duration > results['max']:
            results['max'] = duration
        results['last'] = call.start
    except KeyError:
        CLOCKED[call.function] = {
            'function': call.function,
            'count': 1,
            'total': duration,
            'max': duration,
            'first': call.start,
            'last': call.start
        }


def report(fp=None, reset=False):
    """Reports all clocked function calls"""
    global CLOCKED
    results = {'total': None}
    times = []
    for func_path in sorted(CLOCKED):
        func_results = CLOCKED[func_path]
        func_results['mean'] = func_results['total'] / func_results['count']
        times.extend([func_results['first'], func_results['last']])
        for key in ['first', 'last']:
            del func_results[key]
        results[func_path] = Result(**func_results)
    total = (max(times) - min(times)).total_seconds()
    results['total'] = Result('total', 1, total, total, total)
    if fp:
        with open(fp, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, dialect='excel')
            attrs = ['function', 'count', 'total', 'mean', 'max']
            writer.writerow(attrs)
            for row in results.values():
                writer.writerow([getattr(row, a) for a in attrs])
    if reset:
        for key in list(CLOCKED):
            del CLOCKED[key]
    return results


def clock_all_methods(class_, include_private=False):
    """Clocks all methods in the given class"""
    try:
        clocked = class_.clocked
    except AttributeError:
        clocked = False
    if not clocked:
        for name, method in inspect.getmembers(class_):
            # Never clock magic methods
            if name.startswith('__'):
                continue
            if not include_private and name.startswith('_'):
                continue
            if callable(method):
                try:
                    sig = inspect.signature(method, follow_wrapped=False)
                    if str(sig).startswith('(self'):
                        setattr(class_, name, clock(method))
                except ValueError:
                    pass
        class_.clocked = True
        # Clock parent classes as well
        for parent in class_.__bases__:
            if type(parent) != object:
                clock_all_methods(class_, include_private=include_private)

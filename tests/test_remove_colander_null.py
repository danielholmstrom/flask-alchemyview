# vim: set fileencoding=utf-8 :
from __future__ import absolute_import, division

from flask_alchemyview import _remove_colander_null
import colander as c


def test_remove_colander_null_removes_colander_null():
    assert _remove_colander_null({'a': c.null}) == {}


def test_remove_colander_null_doesnt_remove_string():
    assert _remove_colander_null({'a': 'a', 'b': c.null}) == {'a': 'a'}


def test_remove_colander_null_works_recursively():
    assert _remove_colander_null(
        {'a': {'a': 1, 'b': c.null}}) == {'a': {'a': 1}}

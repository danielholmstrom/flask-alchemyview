# vim: set fileencoding=utf-8 :
from __future__ import absolute_import, division

from flask_alchemyview import _gettext


def test_gettext_simple_string():
    assert _gettext(u'a string') == u'a string'


def test_gettext_positional_args():
    assert _gettext(u'%(0) %(1) (2)', u'one', u'two') == u'one two (2)'


def test_gettext_named_args():
    assert _gettext(u'%(first) %(second) (third)',
                    first=u'one', second=u'two') == u'one two (third)'

# vim: set fileencoding=utf-8 :
"""

*****************
Flask-AlchemyView
*****************

A Flask AlchemyView that makes it a bit easier to manage views for
SQLAlchemy Declarative models. The :class:`flask_alchemyview.AlchemyView` class
extends the very nice `Flask-Classy <https://github.com/apiguy/flask-classy>`_
FlaskView and supports all Flask-Classy FlaskView functionality.

What does it do?
================

The AlchemyView handles GET/POST/PUT/DELETE and listing items for a specific
SQLAlchemy declarative model. Currenctly it assumes JSON requests and returns
JSON responses, but extending it to support HTML generation should not be a
problem, it's just not very interesting for me to do that.

*NOTE!!!* The AlchemyView only supports models with single preimary keys,
composite keys are currently not supported because I cannot descide how to
handle them in the URL.

The session
===========

A AlchemyView uses either :attr:`flask_alchemyview.AlchemyView.session` or, if
that is not set, :attr:`flask_alchemyview.AlchemyView.model`.session. If
neither is set the view will start throwing exceptions, just remember to set
one of them.

Dictalchemy
===========

Model instances are serialized to and from dicts using `dictalchemy
<http://pythonhosted.org/dictalchemy/>`_. When new instances are created the
unserialized JSON will be passed to their constructor.

Colander
========

Input data validation is done with `colander
<http://docs.pylonsproject.org/projects/colander/en/latest/>`_ schemas.

GET an item
===========

In case of a GET item request the view will check if the actual item exists.
If it does the AlchemyView will return that object in JSON form. What the view
does return is determined by either the models dictalchemy settings or settings
in the AlchemyView. The attributes
:attr:`flask_alchemy.AlchemyView.dict_params` and
:attr:`flask_alchemy.AlchemyView.asdict_params` will override the models
default behaviour. The query used to fetch the object is created in
:meth:`flask_alchemyview.AlchemyView._base_query`. That query is always used
for fetching items, so if you want to add joins or other stuff that is the
method that you should override.

See also
--------

    * :func:`flask_alchemyview.AlchemyView.asdict_params`
    * :func:`flask_alchemyview.AlchemyView.dict_params`

PUT an item
===========

Updating an item is pretty basic. If the item exists it will be updated with
the data returned by the update schema. The update schema is either
:attr:flask_alchemy.AlchemyView.update_schema` or
:attr:flask_alchemyview.AlchemyView.schema` if `update_schema` isn't set. If
any SchemaNode in the schema returns colander.null it will be removed from the
update data, None will be preserved. This behaviour cannot be modified at the
moment.

Updating the item will be done by calling `model.fromdict`. The parameters will
be :attr:`flask_alchemy.AlchemyView.fromdict_params`, or
:attr:`flask_alchemy.AlchemyView.dict_params` if `fromdict_params` isn't set.

On validation error a 400 will be returned, on other errors a 500 will be
returned.

Out of the box a AlchemyView is a bit limited in it's update/create
functionality. This is by design, if creating/updating a model is more complex
it's best to not try to do it automagically.

See also
--------

    * :func:`flask_alchemyview.AlchemyView.fromdict_params`
    * :func:`flask_alchemyview.AlchemyView.dict_params`
    * :func:`flask_alchemyview.AlchemyView.update_schema`


POST a new item
===============

When post:ing data the data will be validated by the
:attr:flask_alchemy.AlchemyView.create_schema` or
:attr:flask_alchemyview.AlchemyView.schema` if `create_schema` isn't set.
Colander null values will not be removed. The validated data will be sent to
the model constructor. On validation error an error message will be returned,
on other errors a 500 will be returned.

See also
--------
    * :func:`flask_alchemyview.AlchemyView.create_schema`


DELETE an item
==============

A delete will simply delete the instance if it exists. The delete method is
defined as :meth:`flask_alchemyview.AlchemyView.delete` and
:meth:`flask_alchemyview.AlchemyView._delete`.


Listing items
=============

Listing items is done by GET:ing /ROUTE_BASE/. It takes the arguments 'limit',
'offset', 'sortby' and 'direction'. `sortby` is mapped to
:flask_alchemyview.AlchemyView.sortby_map`. Limit, offset and direction works
like usual. There are defaults values for these and a
:attr:`flask_alchemyview.AlchemyView.max_page_limit` attribute.which limits the
limit.

See also
--------

    * :attr:`flask_alchemyview.AlchemyView.sortby`
    * :attr:`flask_alchemyview.AlchemyView.sortby_map`
    * :attr:`flask_alchemyview.AlchemyView.sort_direction`
    * :attr:`flask_alchemyview.AlchemyView.page_limit`
    * :attr:`flask_alchemyview.AlchemyView.max_page_limit`

Usage
=====

Simple example::

    class SimpleModel(Base):

        __tablename__ = 'simplemodel'

        id = Column(Integer, primary_key=True)

        name = Column(Unicode)

        def __init__(self, name):
            self.name = name


    class SimpleModelSchema(c.MappingSchema):

        name = c.SchemaNode(c.String())


    class SimpleModelView(AlchemyView):
        model = SimpleModel
        schema = SimpleModelSchema
        session = myapp.db

    SimpleModelView.register(app)


"""
from __future__ import absolute_import, division

import re
import json
import datetime
import decimal
import logging
import traceback
import colander
from sqlalchemy.exc import IntegrityError
from flask import Response, url_for, abort, request, redirect
from flask.ext.classy import FlaskView


def _gettext(msg, *args, **kwargs):
    """Dummy translation method used if Flask-Babel isn't installed

    :returns: Formatted string
    """
    return re.sub(r'%\(([a-z0-9_]+)\)', r'{\1}', msg).format(*args,
                                                             **kwargs)

try:
    from flask.ext.babel import gettext
    _ = gettext
except ImportError:
    _ = _gettext


_logger = logging.getLogger('flask.ext.alchemyview')
"""Our logger"""


def _remove_colander_null(result):
    """Removes colaner.null values from a dict or list

    Works recursively.

    :param result: dict or list of values
    :raises: Exception if `result` isn't a dict or list

    :returns: a copy of result with all colander.null values removed
    """
    if isinstance(result, dict):
        rc = {}
        for (k, v) in result.iteritems():
            if isinstance(v, dict) or isinstance(v, list):
                rc[k] = _remove_colander_null(v)
            else:
                if v is not colander.null:
                    rc[k] = v
        return rc
    elif isinstance(result, list):
        return [v for v in result if v is not colander.null]
    else:
        raise Exception("Argument 'result' is not dict or list(%r)" %
                        type(result))


def _exception_to_dict(error):
    """Get a dict from an Exception

    :param error: An Exception.\
            Currently the following exceptions are supported:
            * :class:`sqlalchemy.exc.IntegrityError`
            * :class:`colander.Invalid`

    :returns: Dict with errors. Contains 'message' and 'errors', \
            where 'errors' is a dict containing {'key': unicode message}
    """
    if isinstance(error, IntegrityError):
        m = re.search(r'(Key) \((\w+)\)=\(([^)]*)\) already exists',
                      str(error.orig))
        if m:
            return {u'message': _(u"'%(key)' already exists", key=m.group(2)),
                    'errors': {m.group(2): _(u'Already exists')}}
    elif isinstance(error, colander.Invalid):
        return {u'errors': error.asdict()}

    _logger.debug('ecom.utils._exception_to_dict:'
                  'Got unhandled error: %r:%s\nTraceback: %s' %
                  (error, str(error),
                   traceback.format_exc()))
    print error, str(error), traceback.format_exc()
    return {u'message': _(u'Unknown error'), u'errors': {}}


class _Encoder(json.JSONEncoder):
    """JSON Encoder class that handles conversion for a number of types not
    supported by the default json library


    - datetime.* objects will be converted with their isoformat() function.
    - Decimal will be converted to a unicode string
    - Any object with an asdict() method will be converted to a dict that is
      returned

    :returns: object that can be converted to json
    """

    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        elif isinstance(obj, (decimal.Decimal)):
            return unicode(obj)
        elif hasattr(obj, 'asdict') and callable(getattr(obj, 'asdict')):
            return obj.asdict()
        else:
            return json.JSONEncoder.default(self, obj)


class AlchemyView(FlaskView):
    """View for SQLAlchemy dictable models"""

    JSONEncoder = None
    """The JSON Encoder that should be used to load/dump json"""

    session = None
    """The SQLAlchemy session. If not set self.model.session will be used(for
    those who uses Flask-SQLAlchemy. If that is not set the view will not
    work."""

    model = None
    """SQLAlchemy declarative model"""

    schema = None
    """Colander schema that will be used as both update_schema and
    create_schema if they aren't set"""

    update_schema = None
    """Update schema"""

    create_schema = None
    """Create schema"""

    dict_params = None
    """Will be used instead of asdict_params and fromdict_params if they're not
    set"""

    # asdict_params = None
    """Parameters that will be used when getting an item"""

    # fromdict_params = None
    """Parameters that will be used when updating an item"""

    max_page_limit = 50
    """Max page limit"""

    page_limit = 10
    """Default page limit"""

    sortby = None
    """Default sortby column"""

    sort_direction = 'asc'
    """Default sort direction"""

    sortby_map = None
    """Map of string=>column for sortby"""

    def _json_dumps(self, obj, ensure_ascii=False, **kwargs):
        """Load object from json string

        Uses :attr:`flask_alchemyview.AlchemyView.JSONEncoder` to dump the
        data.

        :param obj: Object that should be dumped

        :returns: JSON string
        :rtype str:
        """
        kwargs['ensure_ascii'] = ensure_ascii
        kwargs['cls'] = self.JSONEncoder
        return json.dumps(obj, **kwargs)

    def _json_loads(self, string, **kwargs):
        """Load json"""
        return json.loads(string, **kwargs)

    def _json_response(self, obj, status=200):
        """Get a json response

        :param obj: Exception OR something that can used by
            :meth:`flask_alchemyview.AlchemyView._json_dumps`
            If this is an exception the status will be
            set to 400 if status is less than 400.
        """
        if isinstance(obj, Exception):
            if status < 400:
                status = 400
            obj = _exception_to_dict(obj)

        return Response(json.dumps(obj),
                        status=status,
                        mimetype='application/json')

    def _json_response_error_message(self, message, status=400):
        return self._json_response({u'message': message}, status)

    def _base_query(self):
        """Get the base query that should be used

        For example add joins here. Default implementation returns
        self.model.query.

        :returns: Sqlalchemy query
        """
        return self._get_session().query(self.model)

    def _item_url(self, item):
        """Get the url to read an item

        :raises: Exception if the items primary key is a composite key
        """
        if len(self.model.__table__.primary_key) != 1:
            raise Exception("AlchemyView doesn't handle models with "
                            "composite primary key")
        primary_key = [(column.name, column.type.python_type)
                       for column in self.model.__table__.primary_key]
        primary_key_name = primary_key[0][0]
        return url_for(self.build_route_name('get'),
                       id=getattr(item, primary_key_name))

    def _get_item(self, id):
        """Get item based on id

        Can handle models with int and string primary keys.

        :raises: Exception if the primary key is a composite or not \
                int or string

        :returns: An item, calls flask.abort(400) if the item isn't found
        """
        primary_key = [(column.name, column.type.python_type)
                       for column in self.model.__table__.primary_key]
        if len(primary_key) != 1:
            raise Exception("AlchemyView doesn't handle models with "
                            "composite primary key")
        primary_key_type = primary_key[0][1]
        primary_key_name = primary_key[0][0]
        if primary_key_type not in (int, str, unicode):
            raise Exception("AlchemyView can only handle int and string "
                            "primary keys not %r" % primary_key_type)
        try:
            if type(id) != primary_key_type:
                id = primary_key_type(id)
        except:
            abort(404)

        item = self._base_query().filter(
            getattr(self.model,
                    primary_key_name) == id).limit(1).first()

        if not item:
            abort(404)

        return item

    def _get_session(self):
        """Get SQLAlchemy session

        :raises: An exception if self.session and self.model.session isn't set

        :returns: SQLAlchemy session
        """
        return self.session or self.model.session

    def _get_schema(self, data):
        """Get basic colander schema

        This schema is used if create_schema or update_schema isn't set.

        :returns: Colander schema for create or update schema
        """
        return self.schema()

    def _get_create_schema(self, data):
        """Get colander schema for create

        :returns: Colander schema for create data
        """
        if getattr(self, 'create_schema', None):
            return self.create_schema()
        else:
            return self._get_schema(data)

    def _get_update_schema(self, data):
        """Get colander update schema

        :returns: Colander schema for create data
        """
        if getattr(self, 'update_schema', None):
            return self.update_schema()
        else:
            return self._get_schema(data)

    def get(self, id):
        """Handles GET requests"""
        return self._json_response(self._get_item(id).
                                   asdict(**getattr(self, 'asdict_params',
                                                    self.dict_params or {})))

    def post(self):
        """Handles POST

        This method will create a model with request data if the data was
        valid. It validates the data with
        :meth:`flask_alchemyview.AlchemyView._get_create_schema`.

        If everything was successfull it will return a 303 redirect to the
        newly created item.

        :returns: A response
        :rtype: :class:`flask.Response`

        """
        session = self._get_session()
        try:
            result = _remove_colander_null(self._get_create_schema(
                request.json).deserialize(request.json))
        except Exception, e:
            session.rollback()
            return self._json_response(e, 400)
        else:
            try:
                item = self.model(**result)
                session.add(item)
            except Exception, e:
                session.rollback()
                return self._json_response(e, 500)
            else:
                try:
                    session.commit()
                except:
                    return self._json_response(e, 500)
                return redirect(self._item_url(item), 303)

    def put(self, id):
        item = self._get_item(id)
        session = self._get_session()
        try:
            result = _remove_colander_null(self._get_update_schema(
                request.json).deserialize(request.json))
            item.fromdict(result,
                          **getattr(self, 'fromdict_params',
                                    self.dict_params or {}))
            session.add(item)
            session.commit()
        except Exception, e:
            return self._json_response(e, 400)

        return redirect(self._item_url(item), 303)

    def _delete(self, id):
        item = self._get_item(id)
        session = self._get_session()
        session.delete(item)
        try:
            session.commit()
        except Exception, e:
            return self._json_response(e, 400)
        # TODO: What should a delete return?
        return self._json_response({})

    delete = _delete

    def index(self):
        """Returns a list

        The response look like this:

        {
            items:[...],
            count: Integer,
            limit: Integer,
            offset: Integer
        }
        """
        try:
            # TODO: Check with a max value
            limit = min(int(request.args.get('limit', self.page_limit)),
                        self.max_page_limit)
        except:
            return self._json_response({u'message': _(u'Invalid limit')}, 400)
        if limit > 100:
            limit = 10
        try:
            offset = int(request.args.get('offset', 0))
        except:
            return self._json_response({u'message': _(u'Invalid offset')},
                                       400)
        try:
            sortby = str(request.args.get('sortby', self.sortby))
        except:
            return self._json_response({u'message': _(u'Invalid sortby')},
                                       400)
        try:
            direction = str(request.args.get('direction', self.sort_direction))
        except:
            return self._json_response({u'message': _(u'Invalid direction')},
                                       400)

        if direction not in ('asc', 'desc'):
            return self._json_response({u'message': _(u'Invalid direction')},
                                       400)

        query = self._base_query()

        # Add sortby
        if self.sortby_map and sortby in self.sortby_map:
            query = query.order_by(getattr(self.sortby_map[sortby],
                                           direction)())
        else:
            if not hasattr(self.model, sortby):
                return self._json_response({u'message': _(u'Invalid sortby')},
                                           400)
            else:
                query = query.order_by(getattr(getattr(self.model,
                                                       sortby), direction)())

        return self._json_response({
            'items': [p.asdict(**getattr(self,
                                         'asdict_params',
                                         self.dict_params or {})) for p in
                      query.limit(limit).offset(offset).all()],
            'count': query.count(),
            'limit': limit,
            'offset': offset})

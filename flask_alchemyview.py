# vim: set fileencoding=utf-8 :
"""

Flask-AlchemyView
~~~~~~~~~~~~~~~~~

Flask view for SQL-Alchemy declarative models.

:copyright: (c) 2013 by Daniel Holmström.
:licence: MIT, see LICENCE for more information.


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
from flask import current_app


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

    Currently the following exceptions are supported:
        * :class:`sqlalchemy.exc.IntegrityError`
        * :class:`colander.Invalid`

    :param error: An Exception

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
    """The SQLAlchemy session

    If not set the session will be taken from the Flask-SQLAlchemy extension.
    If that is missing the view will not work.
    """

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
    """Will be used instead of
    :attr:`AlchemyView.asdict_params` and
    :attr:`AlchemyView.from_params` if they're not set"""

    asdict_params = None
    """Parameters that will be used when getting an item

    The parameters will be used in :meth:`dictalchemy.utils.asdict`.
    """

    fromdict_params = None
    """Parameters that will be used when updating an item

    The parameters will be used in :meth:`dictalchemy.utils.fromdict`.
    """

    max_page_limit = 50
    """Max page limit"""

    page_limit = 10
    """Default page limit"""

    sortby = None
    """Default sortby column

    If not set no sortby will be applied by default in
    :func:`AlchemyView.index`.

    In order for sortby to have any effect it also needs to be set in
    :attr:`AlchemyView.sortby_map`
    """

    sort_direction = 'asc'
    """Default sort direction"""

    sortby_map = None
    """Map of string=>column for sortby

    The values can be anything that will work together with the query returned
    by :meth:`AlchemyView._base_query`. So if there is a join
    in the base query that column, or name of that colum can be mapped to a key
    in the sortby_map.
    """

    def _json_dumps(self, obj, ensure_ascii=False, **kwargs):
        """Load object from json string

        Uses :attr:`AlchemyView.JSONEncoder` to dump the
        data.

        :param obj: Object that should be dumped

        :returns: JSON string
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
            :meth:`AlchemyView._json_dumps`
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
        `self._get_session().query(self.model)`.

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

        :raises: An exception if self.session isn't set and \
                Flask-SQLAlchemy isn't used

        :returns: SQLAlchemy session
        """
        return self.session or current_app.extensions['sqlalchemy'].db.session

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
                                   asdict(**(getattr(self, 'asdict_params',
                                                     self.dict_params or None)
                                             or {})))

    def post(self):
        """Handles POST

        This method will create a model with request data if the data was
        valid. It validates the data with
        :meth:`AlchemyView._get_create_schema`.

        If everything was successful it will return a 303 redirect to the
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
        """Handles PUT"""
        item = self._get_item(id)
        session = self._get_session()
        try:
            result = _remove_colander_null(self._get_update_schema(
                request.json).deserialize(request.json))
            item.fromdict(result,
                          **(getattr(self, 'fromdict_params',
                                     self.dict_params or None) or {}))
            session.add(item)
            session.commit()
        except Exception, e:
            return self._json_response(e, 400)

        return redirect(self._item_url(item), 303)

    def _delete(self, id):
        """Delete an item"""
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
    """Delete an item

    This is just an alias for :meth:`AlchemyView._delete`.
    """

    def index(self):
        """Returns a list

        The response look like this::

            items: [...]
            count: Integer
            limit: Integer
            offset: Integer

        """
        try:
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
            sortby = request.args.get('sortby', None)
            if sortby:
                sortby = str(sortby)
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
        if sortby and self.sortby_map and sortby in self.sortby_map:
            query = query.order_by(getattr(self.sortby_map[sortby],
                                           direction)())

        return self._json_response({
            'items': [p.asdict(**(getattr(self,
                                          'asdict_params',
                                          self.dict_params or None) or {}))
                      for p in
                      query.limit(limit).offset(offset).all()],
            'count': query.count(),
            'limit': limit,
            'offset': offset})

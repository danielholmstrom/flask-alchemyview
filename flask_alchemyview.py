# vim: set fileencoding=utf-8 :
"""
~~~~~~~~~~~~~~~~~
Flask-AlchemyView
~~~~~~~~~~~~~~~~~

Flask view for SQL-Alchemy declarative models.

:copyright: (c) 2013 by Daniel Holmström.
:licence: MIT, see LICENCE for more information.


"""
from __future__ import absolute_import, division

import re
import os
import json
import datetime
import decimal
import logging
import traceback
import colander
from sqlalchemy.exc import IntegrityError
from flask import (Response,
                   url_for,
                   abort,
                   request,
                   redirect,
                   render_template,
                   current_app,
                   )
from flask.ext.classy import FlaskView
from werkzeug.exceptions import HTTPException
from jinja2.exceptions import TemplateNotFound


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
"""The logger that is used. It uses the 'flask.ext.alchemyview' name."""


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
        return {u'errors': error.asdict(),
                u"message": _("Invalid Data")}

    _logger.debug('ecom.utils._exception_to_dict:'
                  'Got unhandled error: %r:%s\nTraceback: %s' %
                  (error, str(error),
                   traceback.format_exc()))
    return {u'message': _(u'Unknown error'), u'errors': {}}


class _JSONEncoder(json.JSONEncoder):
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


class BadRequest(HTTPException):
    """HTTPException class that also contains error data

    This will be raised when a request is invalid, use `Flask.errorhandler()`
    to handle these for HTML responses.

    :ivar data: Dict explaining the error, contains the keys 'message' and \
            'errors'
    """

    def __init__(self, code, data):
        """Create a BadRequest

        If data is an exception it will be converted to a dict, otherwise a
        dict is assumed.
        The description will be set to data['message']

        :param code: HTTP Status code
        :param data: Dict or Exception
        """
        if isinstance(data, Exception):
            self.data = _exception_to_dict(data)
        else:
            self.data = (data[u'message']
                         if u'message' in data
                         else _(u'Unknown error'))
            self.data = data

        self.code = code
        super(BadRequest, self).__init__(self.data[u'message'])


class AlchemyView(FlaskView):
    """View for SQLAlchemy dictable models

    The pre-defined methods will always return JSON, with the mimetype set to
    application/json.
    """

    JSONEncoder = _JSONEncoder
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

    template_suffixes = {'text/html': 'jinja2'}
    """Suffixes for response types, currently 'text/html' is the only one
    supported"""

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

        return Response(self._json_dumps(obj),
                        status=status,
                        mimetype='application/json')

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

    def _get_response_mimetype(self):
        """Get response type from response

        :returns: 'application/json' or 'text/html'
        """
        best = request.accept_mimetypes.best_match(['application/json',
                                                    'text/html'])
        if best == 'application/json' and \
                request.accept_mimetypes[best] > \
                request.accept_mimetypes['text/html']:
            return 'application/json'
        else:
            return 'text/html'

    def _get_template_name(self, name, mimetype):
        """Get template name for a specific mimetype

        The template name is by default get_route_base()/name.suffix, the
        suffixes are stored in :attr:`AlchemyView.template_suffixes`.

        :returns: string
        """
        return os.path.join(self.get_route_base(),
                            '%s.%s' % (name,
                                       self.template_suffixes[mimetype]))

    def _response(self, data, template, status=200):
        """Get a response

        If the response will be rendered with a template and the method
        '_TEMPLATE_template_vars' is set that method will be called and the
        returnvalue will be added to the template parameters.

        :raises: If status is beteen 400 and 500 OR data is an exception a \
                :class:`BadRequest` will be raised.

        :returns: A json or html response, based on the request accept headers
        """
        mimetype = self._get_response_mimetype()
        if mimetype == 'application/json':
            return self._json_response(data, status)
        else:
            if isinstance(data, Exception):
                if status < 400:
                    status = 400
            if status >= 400:
                raise BadRequest(status, data)
            else:
                fn_name = 'before_%s_render' % template

                if hasattr(self, fn_name) and callable(getattr(self, fn_name)):
                    kwargs = getattr(self, fn_name)(data) or {}
                else:
                    kwargs = {}
                try:
                    return render_template(self._get_template_name(template,
                                                                   mimetype),
                                           data=data,
                                           **kwargs)
                except TemplateNotFound:
                    raise BadRequest(406, {'message':
                                           _('Not a valid Accept-Header')})

    def get(self, id):
        """Handles GET requests"""
        return self._response(self._get_item(id).
                              asdict(**(getattr(self, 'asdict_params',
                                                self.dict_params or None)
                                        or {})), 'get')

    def post(self):
        """Handles POST

        This method will create a model with request data if the data was
        valid. It validates the data with
        :meth:`AlchemyView._get_create_schema`.

        If everything was successful it will return a 303 redirect to the
        newly created item.

        If any error except validation errors are encountered a 500 will be
        returned.

        :returns: A response
        :rtype: :class:`flask.Response`

        """
        session = self._get_session()
        try:
            result = _remove_colander_null(self._get_create_schema(
                request.json).deserialize(request.json))
        except Exception, e:
            session.rollback()
            return self._response(e, 'post', 400)
        else:
            try:
                item = self.model(**result)
                session.add(item)
            except Exception, e:
                session.rollback()
                return self._response(e, 'post', 500)
            else:
                try:
                    session.commit()
                except:
                    return self._response(e, 'post', 500)
                return redirect(self._item_url(item), 303)

    def put(self, id):
        """Handles PUT

        If any error except validation errors are encountered a 500 will be
        returned.

        """
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
        except colander.Invalid, e:
            return self._response(e, 'put', 400)
        except Exception, e:
            return self._response(e, 'put', 500)
        else:
            return redirect(self._item_url(item), 303)

    def _delete(self, id):
        """Delete an item"""
        item = self._get_item(id)
        session = self._get_session()
        session.delete(item)
        try:
            session.commit()
        except Exception, e:
            return self._response(e, 'delete', 400)
        # TODO: What should a delete return?
        return self._response({}, 'delete', 200)

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
            return self._response({u'message': _(u'Invalid limit')},
                                  'index',
                                  400)
        if limit > 100:
            limit = 10
        try:
            offset = int(request.args.get('offset', 0))
        except:
            return self._response({u'message': _(u'Invalid offset')},
                                  'index',
                                  400)
        try:
            sortby = request.args.get('sortby', None)
            if sortby:
                sortby = str(sortby)
        except:
            return self._response({u'message': _(u'Invalid sortby')},
                                  'index',
                                  400)
        try:
            direction = str(request.args.get('direction', self.sort_direction))
        except:
            return self._response({u'message': _(u'Invalid direction')},
                                  'index',
                                  400)

        if direction not in ('asc', 'desc'):
            return self._response({u'message': _(u'Invalid direction')},
                                  'index',
                                  400)

        query = self._base_query()

        # Add sortby
        if sortby and self.sortby_map and sortby in self.sortby_map:
            query = query.order_by(getattr(self.sortby_map[sortby],
                                           direction)())

        return self._response({
            'items': [p.asdict(**(getattr(self,
                                          'asdict_params',
                                          self.dict_params or None) or {}))
                      for p in
                      query.limit(limit).offset(offset).all()],
            'count': query.count(),
            'limit': limit,
            'offset': offset},
            'index')

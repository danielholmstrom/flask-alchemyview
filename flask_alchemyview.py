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

from flask.ext.babel import gettext as _


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
            return {u'message': _(u"'%(key)s' already exists", key=m.group(2)),
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

        The description will be set to data['message'] or 'Unknown Error'.

        :param code: HTTP Status code
        :param data: Dict of information about the error
        """
        self.data = (data[u'message']
                     if u'message' in data
                     else _(u'Unknown error'))
        self.data = data

        self.code = code
        super(BadRequest, self).__init__(self.data[u'message'])


class AlchemyViewMixin(FlaskView):
    """View mixin for SQLAlchemy dictable models together with FlaskView

    This view does not expose any methods that will be routed by
    :class:`flask.ext.classy.FlaskView`.
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
    :attr:`AlchemyViewMixin.asdict_params` and
    :attr:`AlchemyViewMixin.from_params` if they're not set"""

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
    :func:`AlchemyViewMixin.index`.

    In order for sortby to have any effect it also needs to be set in
    :attr:`AlchemyViewMixin.sortby_map`
    """

    sort_direction = 'asc'
    """Default sort direction"""

    sortby_map = None
    """Map of string=>column for sortby

    The values can be anything that will work together with the query returned
    by :meth:`AlchemyViewMixin._base_query`. So if there is a join
    in the base query that column, or name of that colum can be mapped to a key
    in the sortby_map.
    """

    template_suffixes = {'text/html': 'jinja2'}
    """Suffixes for response types, currently 'text/html' is the only one
    supported"""

    integrity_error_status_code = 400
    """The status code an :class:`sqlalchemy.exc.IntegrityError` should
    return"""

    def _json_dumps(self, obj, ensure_ascii=False, **kwargs):
        """Load object from json string

        Uses :attr:`AlchemyViewMixin.JSONEncoder` to dump the
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

    def _exception_to_dict(self, exception):
        """Convert an Exception to a dict

        This method is used to create json responses when an Exception occurs.
        Default implementation is :meth:`_exception_to_dict`.

        :param exception: The Exception

        :returns: Dict created from `exception`
        """
        return _exception_to_dict(exception)

    def _bad_html_request(self, code, data=None):
        """Create a :class:`BadRequest`

        If `data` is an Exception :meth:`AlchemyViewMixin._exception_to_dict`
        will be used to convert it to a dict.

        :param code: Status code
        :param data: Dict or Exception

        :returns: a :class:`BadRequest`
        """

        data = data or {}
        if isinstance(data, Exception):
            data = _exception_to_dict(data)
        return BadRequest(code, data)

    def _json_response(self, obj, status=200):
        """Get a json response

        :param obj: Exception OR something that can used by
            :meth:`AlchemyViewMixin._json_dumps`
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

    def _base_query(self, **kwargs):
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
                       **{primary_key_name: getattr(item, primary_key_name)})

    def _get_item(self, **kwargs):
        """Get item based on kwargs

        This is used in :meth:`AlchemyViewMixin.put` and
        :meth:`AlchemyViewMixin.get`, not in :meth:`AlchemyViewMixin.index`.
        Can handle models with int or string primary key.

        :raises: Exception if the primary key is a composite or not \
                int or string

        :returns: An item, calls flask.abort(404) if the item isn't found
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
        pk_value = kwargs.get(primary_key_name, None)

        if pk_value is None:
            abort(404)

        try:
            if type(pk_value) != primary_key_type:
                pk_value = primary_key_type(pk_value)
        except:
            abort(404)

        item = self._base_query().filter(
            getattr(self.model,
                    primary_key_name) == pk_value).limit(1).first()

        if not item:
            abort(404)

        return item

    def _get_create_item(self, **kwargs):
        """Get an item that should be used during create

        Default implementation creates a new `AlchemyViewMixin.model` instance
        using kwargs.

        kwargs::

            Arguments that has been passed through the create schema

        :returns: SQLAlchemy model
        """
        return self.model(**kwargs)

    def _populate_existing_item(self, item, data, route_arguments):
        """Populate an existing item from request data

        This method is used by :meth:`AlchemyViewMixin._put` to populate an
        item from request data.

        :param item: The item read from database
        :param data: Request data deserialized through the update schema
        :param route_arguments: Route arguments

        :returns: item or another instance that will be added to the database
        """
        item.fromdict(data,
                      **(getattr(self, 'fromdict_params',
                                 self.dict_params or None) or {}))
        return item

    def _update_item(self, item, data, route_arguments):
        """Update an item based on request data

        A rollback will be issued if an exception is raised from this method.
        Any documented exception is fine to raise from this method.

        :param item: The item read from database
        :param data: Request data
        :param route_arguments: Route arguments

        :raises: :class:`sqlalchemy.ext.IntegrityError` if an integrity error \
        was encoutered(results in a 400)
        :raises: :class:`colander.Invalid` if a validation error was \
        encountered(results in a 400)
        :raises: :class:`Exception` On any other error(results in a 500)

        :returns: The item
        """
        return self._populate_existing_item(item, data, route_arguments)

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

        :param data: dict with data `put` was called with

        :returns: Colander schema for create or update schema
        """
        return self.schema()

    def _get_create_schema(self, data, route_arguments):
        """Get colander schema for create

        :param data: dict with data used during create

        :returns: Colander schema for create data
        """
        if getattr(self, 'create_schema', None):
            return self.create_schema()
        else:
            return self._get_schema(data)

    def _get_update_schema(self, data, pk):
        """Get colander update schema

        **NOTE**

        The order of the arguments here `pk` and `data` is will most likely
        change, so use named parameters for this method. The current order is
        because of backwards compability.

        If `update_schema` is set that schema will be returned, otherwise
        `_get_schema` will be called.

        :param data: The data `put` was called with
        :param pk: The primary key `put` was called with

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
        suffixes are stored in :attr:`AlchemyViewMixin.template_suffixes`.

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
                :class:`BadRequest` will be raised if the client wants an \
                HTML response

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
                raise self._bad_html_request(status, data)
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
                    raise self._bad_html_request(
                        406, {'message':
                              _('Not a valid Accept-Header')})

    def _get(self, **kwargs):
        """Handles GET requests

        Reads the item from database by calling `_get_item()` and
        calls :meth:`dictalchemy.asdict` on that item using
        :attr:`asditc_params` or :attr:`dict_params` as argument.

        """
        return self._response(self._get_item(**kwargs).
                              asdict(**(getattr(self, 'asdict_params',
                                                self.dict_params or None)
                                        or {})), 'get')

    def _get_create_data(self, request_arguments, route_arguments):
        """Get create data based on request_arguments and route_arguments

        Default implementation ignores `route_arguments` ans simply returns the
        request_arguments.

        :param request_arguments: dict of request data
        :param route_arguments: dict of arguments from routing

        :return: dict of data used for creating a new item
        """

        return request_arguments

    def _post(self, data, route_arguments):
        """Handles POST

        This method will create a model with request data if the data was
        valid. It validates the data with
        :meth:`AlchemyViewMixin._get_create_schema`.

        If everything was successfull it will return a 303 redirect to the
        newly created item.

        If any error except validation errors are encountered a 500 will be
        returned.

        :param data: dict of request data
        :param route_arguments: dict of route arguments

        :returns: A response
        :rtype: :class:`flask.Response`

        """
        session = self._get_session()
        create_data = self._get_create_data(data, route_arguments)
        try:
            result = _remove_colander_null(self._get_create_schema(
                data, route_arguments).deserialize(create_data))
        except Exception, e:
            session.rollback()
            return self._response(e, 'post', 400)
        else:
            try:
                item = self._get_create_item(**result)
                session.add(item)
            except Exception, e:
                session.rollback()
                return self._response(e, 'post', 500)
            else:
                try:
                    session.commit()
                except IntegrityError, e:
                    return self._response(e, 'post',
                                          self.integrity_error_status_code)
                except Exception, e:
                    return self._response(e, 'post', 500)
                return redirect(self._item_url(item), 303)

    def _put(self, **kwargs):
        """Handles PUT

        If any error except validation errors are encountered a 500 will be
        returned.

        """

        session = self._get_session()
        try:
            # item is read before validation etc. because we want a 404 if the
            # item doesn't exist regardless of the validity of the parameters,
            # which would return a 400 so don't change order here.
            item = self._get_item(**kwargs)
            result = _remove_colander_null(self._get_update_schema(
                data=request.json,
                pk=kwargs
            ).deserialize(request.json))
            item = self._update_item(item, result, kwargs)
            session.add(item)
            session.commit()
        except IntegrityError, e:
            session.rollback()
            return self._response(e, 'put',
                                  self.integrity_error_status_code)
        except colander.Invalid, e:
            session.rollback()
            return self._response(e, 'put', 400)
        except HTTPException, e:
            session.rollback()
            return e
        else:
            return redirect(self._item_url(item), 303)

    def _delete(self, **kwargs):
        """Delete an item

        :param kwargs: Is sent to `_get_item`
        """
        item = self._get_item(**kwargs)
        session = self._get_session()
        session.delete(item)
        try:
            session.commit()
        except Exception, e:
            return self._response(e, 'delete', 400)
        # TODO: What should a delete return?
        return self._response({}, 'delete', 200)

    def _list(self, request_arguments, route_arguments=None):
        """Returns a list of items

        The response look like this::

            items: [...]
            count: Integer
            limit: Integer
            offset: Integer

        :param request_arguments: The request arguments
        :param route_arguments: Route arguments passed on to \
                :meth:`AlchemyViewMixinMixin:_base_query`
        """
        route_arguments = route_arguments or {}
        try:
            limit = min(int(request_arguments.get('limit', self.page_limit)),
                        self.max_page_limit)
        except:
            return self._response({u'message': _(u'Invalid limit')},
                                  'index',
                                  400)
        if limit > 100:
            limit = 10
        try:
            offset = int(request_arguments.get('offset', 0))
        except:
            return self._response({u'message': _(u'Invalid offset')},
                                  'index',
                                  400)
        try:
            sortby = request_arguments.get('sortby', None)
            if sortby:
                sortby = str(sortby)
        except:
            return self._response({u'message': _(u'Invalid sortby')},
                                  'index',
                                  400)
        try:
            direction = str(request_arguments.get('direction',
                                                  self.sort_direction))
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


class AlchemyView(AlchemyViewMixin):
    """Standard view that exposes index, get, put, post and delete"""

    def get(self, id):
        """Standard read item GET implementation

        Calls :meth:`AlchemyViewMixin._get`
        """
        return self._get(id=id)

    def post(self):
        """Standard POST implementation

        Calls :meth:`AlchemyViewMixin._post`
        """
        return self._post(request.json, {})

    def put(self, id):
        """Standard PUT implementation

        Calls :meth:`AlchemyViewMixin._put`
        """
        return self._put(id=id)

    def delete(self, id):
        """Standard DELETE implementation

        Calls :meth:`AlchemyViewMixin._delete`
        """
        return self._delete(id=id)

    def index(self):
        """Standard list GET implementation

        Calls :meth:`AlchemyViewMixin._list`
        """
        return self._list(request.args)

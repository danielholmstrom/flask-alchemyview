.. module:: flask.ext.alchemyview

Flask-AlchemyView
=================

A Flask ModelView that makes it a bit easier to manage views for
SQLAlchemy Declarative models. The :class:`AlchemyView` class
extends the very nice `Flask-Classy <https://github.com/apiguy/flask-classy>`_
FlaskView and supports all Flask-Classy FlaskView functionality.

Flask-AlchemyView uses `colander <http://docs.pylonsproject.org/projects/colander/en/latest/>`_ for validation and `dictalchemy <http://pythonhosted.org/dictalchemy/>`_ for updating/creating/reading models.

The session
-----------

A AlchemyView uses either :attr:`AlchemyView.session` or, if
that is not set, the session from Flask-SQLAlchemy(new since v0.1.3). The prefered way to access the session is to use the Flask-SQLAlchemy session.

Using AlchemyView without Flask-SQLAlchemy
------------------------------------------

This is not recommended but if Flask-SQLAlchemy is not used the session can be set on :class:`AlchemyView` directly. Be aware of that this will probably create problems if :class:`AlchemyView` is used by several applications.

Using AlchemyView with Flask-SQLAlchemy
---------------------------------------

Nothing needs to be done in order to use Flask-SQLAlchemy. However, db.Model should be made dictable.

Setup Flask-SQLAlchemy::

    ...
    from flask import Flask
    app = Flask(__name__)

    from flask.ext.sqlalchemy import SQLAlchemy

    db = SQLAlchemy(app)

    from dictalchemy import make_class_dictable
    make_class_dictable(db.Model)


Responses
---------

.. note:: New in 0.1.4

AlchemyView will return json or HTML depending on the HTTP Accept Header. When returning HTML the template used will be determined by :meth:`AlchemyView._get_template_name`. The response data will be passed to the template in the parameter `data`.

Providing extra variables for a template
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the response is a 200 it's possible to provide extra parameters to the template By adding a method called 'before_<view method>_render'. If that method returns anything it must be a dict containing parameters that will be passed to the template.

Adding `is_owner` parameter to a GET request template::

    def before_get_render(self, data):
        return {'is_owner': data[owner_id'] === current_user.id}

Missing templates
^^^^^^^^^^^^^^^^^

If a template is missing a 406 will be returned, not a 500.

Errors
------

.. note:: New in 0.1.4

If an error occurs and json is returned a dict containing 'message' and 'errors' will be returned. If html is returned a :class:`BadRequest` is raised.


Using AlchemyView
-----------------

Lets start with a simple model, a user::

    class User(Base):
        id = Column(Integer, primary_key)
        name = Column(Unicode)
        email = Column(Unicode)


The colander schema looks like this::

    import colander as c

    class UserSchema(c.MappingSchema):
        name = c.SchemaNode(c.String())
        email = c.SchemaNode(c.String())

The View::

    class UserView(AlchemyView):
        model = UserModel
        schema = UserSchema

    UserView.register(app)

After this the following routes has been defined:

    * GET /user/[ID]
    * POST /user/
    * PUT /user/[ID]
    * DELETE /user/[ID]
    * GET /user/

So far so good, but that can easily be done without AlchemyView. So why use AlchemyView? Well, it's pretty configurable. There is support for different schemas depending on weather a PUT or POST is made, it can follow relationships on GET, and to some extent on PUT and POST also. It can take `limit`, `offset`, `sortby` and `direction` arguments when listing.

GET an item
^^^^^^^^^^^

In case of a GET item request the view will check if the actual item exists.
If it does the AlchemyView will return that object in JSON form.

What is returned by GET(individual item or a list) is defined by the parameters :attr:`AlchemyView.dict_params` and :attr:`AlchemyView.asdict_params`. If non of them is set :func:`dictalchemy.utils.asdict` will be called on the model without parameters.

The method :meth:`AlchemyView._base_query` can be overridden in order to add joins, exclude/include columns etc. The returned query is the one that will be used when performing a GET.

Examples
""""""""

Returning only a specific attribute::

    asdict_params = {'only': ['name']}

Following a relationship::

    asdict_params = {'follow': {'group':{}}}

Adding a join to the query::

    def _base_query(self):
        return self.session.query(User).join(Group)


PUT an item
^^^^^^^^^^^

Updating an item is pretty basic. If the item exists it will be updated with
the data returned by the update schema. The update schema is either
:attr:`AlchemyView.update_schema` or
:attr:`AlchemyView.schema` if `update_schema` isn't set. If
any SchemaNode in the schema returns colander.null it will be removed from the
update data, None will be preserved. This behaviour cannot be modified at the
moment.

Updating the item will be done by calling `fromdict()` on :attr:`AlchemyView.model`. The parameters will be :attr:`AlchemyView.fromdict_params`, or
:attr:`AlchemyView.dict_params` if `fromdict_params` isn't set.

On validation error a 400 will be returned, on other errors a 500 will be
returned.

Out of the box a AlchemyView is a bit limited in it's update/create
functionality. This is by design, if creating/updating a model is more complex
it's best to not try to do it automagically.

See also
""""""""

    * :attr:`AlchemyView.fromdict_params`
    * :attr:`AlchemyView.dict_params`
    * :attr:`AlchemyView.update_schema`


POST a new item
^^^^^^^^^^^^^^^

When post:ing data the data will be validated by
:attr:`AlchemyView.create_schema` or
:attr:`AlchemyView.schema` if `create_schema` isn't set.
Colander null values will not be removed. The validated data will be sent to
the model constructor. On validation error an error message will be returned,
on other errors a 500 will be returned.

See also
""""""""

    * :func:`AlchemyView.create_schema`

DELETE an item
^^^^^^^^^^^^^^

A delete will simply delete the instance if it exists. The delete method is
defined as :meth:`AlchemyView.delete` and
:meth:`AlchemyView._delete`.

Listing items
^^^^^^^^^^^^^

The listing URL takes the additional parameters `limit`, `offset`, `sortby` and `direction`. The View has a `max_page_limit` attribute that ensures that `limit` can't be set to high.

Sorting a list
""""""""""""""

If `sortby` isn't set the `sortby` attribute will be used. It that is set to None no sorting will be done. The `sortby` argument is checked against `sortby_map` which is a map of `string`: `expression`. The expression must be something that can be inserted into the _base_query, so either a column or a valid string. If the `sortby` parameter is not found in `sortby_map` a 400 will be returned.

sortby_map Example::

    sortby_map = {'name': User.name, 'group_id': 'Group.id'}

See also
""""""""

    * :attr:`AlchemyView.sortby`
    * :attr:`AlchemyView.sortby_map`
    * :attr:`AlchemyView.sort_direction`
    * :attr:`AlchemyView.page_limit`
    * :attr:`AlchemyView.max_page_limit`

API
---

.. autoclass:: flask.ext.alchemyview.AlchemyView
    :members:
    :private-members:
.. autoclass:: flask.ext.alchemyview.BadRequest


Source
------

The source is hosted on `http://github.com/danielholmstrom/flask-alchemyview <http://github.com/danielholmstrom/flask-alchemyview>`_.

License
-------

Flask-AlchemyView is released under the MIT license.

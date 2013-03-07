*****************
Flask-AlchemyView
*****************

A Flask AlchemyView that makes it a bit easier to manage views for
SQLAlchemy Declarative models. The `flask_alchemyview.AlchemyView` class
extends the very nice `Flask-Classy <https://github.com/apiguy/flask-classy>`_
FlaskView and supports all Flask-Classy FlaskView functionality.

What does it do?
================

The AlchemyView handles GET/POST/PUT/DELETE and listing items for a specific
SQLAlchemy declarative model. Currenctly it assumes JSON requests and returns
JSON responses, but extending it to support HTML generation should not be a
problem, it's just not very interesting for me to do that.

*NOTE!!!* The AlchemyView only supports models with single primary keys,
composite keys are currently not supported because I cannot descide how to
handle them in the URL.

The session
===========

A AlchemyView uses either `flask_alchemyview.AlchemyView.session` or, if
that is not set, `flask_alchemyview.AlchemyView.model`.session. If
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
`flask_alchemy.AlchemyView.dict_params` and
`flask_alchemy.AlchemyView.asdict_params` will override the models
default behaviour. The query used to fetch the object is created in
`flask_alchemyview.AlchemyView._base_query`. That query is always used
for fetching items, so if you want to add joins or other stuff that is the
method that you should override.

See also
--------

    * `flask_alchemyview.AlchemyView.asdict_params`
    * `flask_alchemyview.AlchemyView.dict_params`

PUT an item
===========

Updating an item is pretty basic. If the item exists it will be updated with
the data returned by the update schema. The update schema is either
flask_alchemy.AlchemyView.update_schema` or
flask_alchemyview.AlchemyView.schema` if `update_schema` isn't set. If
any SchemaNode in the schema returns colander.null it will be removed from the
update data, None will be preserved. This behaviour cannot be modified at the
moment.

Updating the item will be done by calling `model.fromdict`. The parameters will
be `flask_alchemy.AlchemyView.fromdict_params`, or
`flask_alchemy.AlchemyView.dict_params` if `fromdict_params` isn't set.

On validation error a 400 will be returned, on other errors a 500 will be
returned.

Out of the box a AlchemyView is a bit limited in it's update/create
functionality. This is by design, if creating/updating a model is more complex
it's best to not try to do it automagically.

See also
--------

    * `flask_alchemyview.AlchemyView.fromdict_params`
    * `flask_alchemyview.AlchemyView.dict_params`
    * `flask_alchemyview.AlchemyView.update_schema`


POST a new item
===============

When post:ing data the data will be validated by the
flask_alchemy.AlchemyView.create_schema` or
flask_alchemyview.AlchemyView.schema` if `create_schema` isn't set.
Colander null values will not be removed. The validated data will be sent to
the model constructor. On validation error an error message will be returned,
on other errors a 500 will be returned.

See also
--------
    * `flask_alchemyview.AlchemyView.create_schema`


DELETE an item
==============

A delete will simply delete the instance if it exists. The delete method is
defined as `flask_alchemyview.AlchemyView.delete` and
`flask_alchemyview.AlchemyView._delete`.


Listing items
=============

Listing items is done by GET:ing /ROUTE_BASE/. It takes the arguments 'limit',
'offset', 'sortby' and 'direction'. `sortby` is mapped to
:flask_alchemyview.AlchemyView.sortby_map`. Limit, offset and direction works
like usual. There are defaults values for these and a
`flask_alchemyview.AlchemyView.max_page_limit` attribute.which limits the
limit.

See also
--------

    * `flask_alchemyview.AlchemyView.sortby`
    * `flask_alchemyview.AlchemyView.sortby_map`
    * `flask_alchemyview.AlchemyView.sort_direction`
    * `flask_alchemyview.AlchemyView.page_limit`
    * `flask_alchemyview.AlchemyView.max_page_limit`

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


More documentation can be found on `pypi <http://pythonhosted.org/Flask-AlchemyView/flask_alchemyview.html>`_.

#####
Intro
#####

A Flask ModelView that makes it a bit easier to manage views for
SQLAlchemy Declarative models. The `flask_alchemyview.AlchemyView` class
extends the very nice `Flask-Classy <https://github.com/apiguy/flask-classy>`_
FlaskView and supports all Flask-Classy FlaskView functionality.

Flask-AlchemyView uses `colander <http://docs.pylonsproject.org/projects/colander/en/latest/>`_ for validation and `dictalchemy <http://pythonhosted.org/dictalchemy/>`_ for updating/creating/reading models.

More documentation can be found at `pipy <http://pythonhosted.org/Flask-AlchemyView/>`_.

Using Flask-SQLAlchemy
======================

In order to use Flask-SQLAlchemy some setup is needed. First of all we want the Model to be dictable. The AlchemyViews should also have session set.

Setup Flask-SQLAlchemy::

    ...
    from flask import Flask
    app = Flask(__name__)

    from flask.ext.sqlalchemy import SQLAlchemy

    db = SQLAlchemy(app)

    from dictalchemy import make_class_dictable
    make_class_dictable(db.Model)

    from flask.ext.alchemyview import AlchemyView
    AlchemyView.session = db.session


Using AlchemyView
=================

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

Using the AlchemyView::

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

Defining what GET should return
-------------------------------

What is returned by GET(individual item or a list) is defined by the parameters `dict_params` and `asdict_params`. If non of them is set asdict() will be called on the model without parameters.

The method `AlchemyView._base_query()` can be overridden in order to add joins, exclude/include columns etc. The returned query is the one that will be used when performing a GET.

Examples
^^^^^^^^

Returning only a specific attribute::

    asdict_params = {'only': ['name']}

Following a relationship::

    asdict_params = {'follow': {'group':{}}}

Adding a join to the query::

    def _base_query(self):
        return self.session.query(User).join(Group)


Controlling POST and PUT
------------------------

POST and PUT will use `dict_params`, `fromdict_params` to create/update items.
The schemas will be taken from `schema`, `create_schema` or `update_schema`.

The `create_schema` is actually returned by the method `_get_create_schema()`, which will get all parameters as argument. By overriding `_get_create_schema()` it's possibly to handle situations where for example different types of a model requires different schemas. The same goes for `update_schema`.


Listing items
-------------

The listing URL takes the additional parameters `limit`, `offset`, `sortby` and `direction`. The View has a `max_page_limit` attribute that ensures that `limit` can't be set to high.

Sorting a list
^^^^^^^^^^^^^^

If `sortby` isn't set the `sortby` attribute will be used. It that is set to None no sorting will be done. The `sortby` argument is checked against `sortby_map` which is a map of `string`: `expression`. The expression must be something that can be inserted into the _base_query, so either a column or a valid string. If the `sortby` parameter is not found in `sortby_map` a 400 will be returned.

sortby_map Example::

    sortby_map = {'name': User.name, 'group_id': 'Group.id'}

License
=======

dictalchemy is released under the MIT license.

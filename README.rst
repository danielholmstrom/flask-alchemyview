Flask-AlchemyView
~~~~~~~~~~~~~~~~~

A Flask ModelView that handles SQLAlchemy Declarative models. It assumes JSON
requests and returns JSON responses.


Data validation
---------------

Data validation is done with `colander
<http://docs.pylonsproject.org/projects/colander/en/latest/>`_ schemas.


JSON
----

Model instances are serialized to and from dicts using `dictalchemy
<http://pythonhosted.org/dictalchemy/>`_. When new instances are created the
unserialized JSON will be passed to their constructor.

Usage
-----

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


The session needs to be set on the view if it's not set on the model.

# vim: set fileencoding=utf-8 :
from __future__ import absolute_import, division

import json
import unittest

from flask import Flask, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.alchemyview import AlchemyView

from dictalchemy import make_class_dictable
import colander as c

SQLALCHEMY_DATABASE_URI = 'sqlite://'

app = Flask(__name__)
app.config.from_object(__name__)
db = SQLAlchemy(app)
make_class_dictable(db.Model)


class SimpleModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)

    def __init__(self, name):
        self.name = name


class SimpleModelSchema(c.MappingSchema):

    name = c.SchemaNode(c.String())


class SimpleModelView(AlchemyView):
    model = SimpleModel
    schema = SimpleModelSchema

db.create_all()
SimpleModelView.register(app)


class TestSimpleModel(unittest.TestCase):

    def setUp(self):
        AlchemyView.session = db.session
        self.ctx = app.test_request_context()
        self.ctx.push()
        self.client = app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def test_get(self):
        # Create the model
        response = self.client.post(url_for('SimpleModelView:post'),
                                    content_type='application/json',
                                    headers=[('Accept', 'application/json')],
                                    data=json.dumps({u'name': u'a name'}),
                                    follow_redirects=False)
        assert response.status_code == 303
        model_id = int(response.location.split('/')[4])
        model = db.session.query(SimpleModel).get(model_id)
        assert model
        assert dict(model) == {u'name': u'a name', u'id': model_id}
        # Get the model
        response = self.client.get(url_for('SimpleModelView:get', id=model_id),
                                   headers=[('Accept', 'application/json')],
                                   content_type='application/json')
        assert response.status_code == 200
        assert json.loads(response.data.decode('utf-8'))['name'] == u'a name'

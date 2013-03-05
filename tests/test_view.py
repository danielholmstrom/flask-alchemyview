# vim: set fileencoding=utf-8 :
from __future__ import absolute_import, division

import unittest
import json
from flask import (
    Flask,
    url_for,
)

from flask_alchemyview import AlchemyView

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Unicode,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import colander as c
from dictalchemy import DictableModel


engine = create_engine('sqlite://')

Base = declarative_base(cls=DictableModel)


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
    session = None


class TestSimpleModel(unittest.TestCase):
    """Test a simple model"""

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.session = self.Session()
        self.app = Flask('test_view')
        SimpleModelView.register(self.app)
        SimpleModelView.session = self.session
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def json_get(self, url, follow_redirects=False):
        """GET json data"""
        return self.client.get(url,
                               content_type='application/json',
                               follow_redirects=follow_redirects)

    def json_post(self, url, data, follow_redirects=False):
        """Post json data"""
        return self.client.post(url,
                                data=json.dumps(data),
                                content_type='application/json',
                                follow_redirects=follow_redirects)

    def json_put(self, url, data, follow_redirects=False):
        """Put json data"""
        return self.client.put(url,
                               data=json.dumps(data),
                               content_type='application/json',
                               follow_redirects=follow_redirects)

    def json_delete(self, url, data=None, follow_redirects=False):
        """Delete request"""
        return self.client.delete(url,
                                  data=json.dumps(data),
                                  content_type='application/json',
                                  follow_redirects=follow_redirects)

    def assert_redirects(self, request, location, status_code=None):
        """Assert that a request redirects"""
        if status_code is not None:
            assert request.status_code == status_code
        else:
            assert request.status_code in (301, 302, 303)
        assert request.location == location

    def test_get_url(self):
        assert url_for('SimpleModelView:get', id=1) == '/simplemodel/1'

    def test_item_url(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        assert SimpleModelView()._item_url(m) == url_for('SimpleModelView:get',
                                                         id=m.id)

    def test_get(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        assert json.loads(self.json_get(url_for('SimpleModelView:get',
                                                id=m.id)).data) == dict(m)

    def test_get_non_existing(self):
        model_id = 1223213124
        model = self.session.query(SimpleModel).get(model_id)
        assert not model
        response = self.json_get(url_for('SimpleModelView:get', id=model_id))
        assert response.status_code == 404

    def test_get_invalid_id(self):
        response = self.json_get(url_for('SimpleModelView:get',
                                         id=u'a string'))
        assert response.status_code == 404

    def test_post(self):
        response = self.json_post(url_for('SimpleModelView:post'),
                                  {'name': 'a name'})
        self.assert_redirects(response, response.location)
        model_id = int(response.location.split('/')[4])
        model = self.session.query(SimpleModel).get(model_id)
        assert model
        assert dict(model) == {u'name': u'a name', u'id': model_id}

    def test_post_with_missing_data(self):
        response = self.json_post(url_for('SimpleModelView:post'), {})
        assert response.status_code == 400
        assert u'name' in json.loads(response.data)['errors']

    def test_put(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        model_id = m.id
        response = self.json_put(url_for('SimpleModelView:put', id=model_id),
                                 {'name': 'new name'})
        self.assert_redirects(response, response.location)
        m = self.session.query(SimpleModel).get(model_id)
        assert dict(m) == {u'name': u'new name', u'id': model_id}

    def test_put_non_existing(self):
        model_id = 1223213124
        model = self.session.query(SimpleModel).get(model_id)
        assert not model
        response = self.json_put(url_for('SimpleModelView:put',
                                         id=model_id), {})
        assert response.status_code == 404

    def test_delete_non_existing(self):
        model_id = 1223213124
        model = self.session.query(SimpleModel).get(model_id)
        assert not model
        response = self.json_get(url_for('SimpleModelView:delete',
                                         id=model_id))
        assert response.status_code == 404

    def test_delete(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        model_id = m.id
        response = self.json_delete(url_for('SimpleModelView:put',
                                            id=model_id))
        response.status_code == 200
        m = self.session.query(SimpleModel).get(model_id)
        assert not m

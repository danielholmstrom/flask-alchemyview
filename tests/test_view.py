# vim: set fileencoding=utf-8 :
from __future__ import absolute_import, division

import unittest
import json
import datetime
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
    DateTime,
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

    created = Column(DateTime)
    # Used to test JSONEncoder

    def __init__(self, name):
        self.name = name


class SimpleModelSchema(c.MappingSchema):

    name = c.SchemaNode(c.String())


class SimpleModelView(AlchemyView):
    model = SimpleModel
    schema = SimpleModelSchema
    session = None
    max_page_limit = 20


class TestSimpleModel(unittest.TestCase):
    """Test a simple model"""

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.session = self.Session()
        self.app = Flask('test_view', template_folder="tests/templates")
        SimpleModelView.register(self.app)
        SimpleModelView.session = self.session
        self.session.query(SimpleModel).delete()
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def json_get(self, url, follow_redirects=False):
        """GET json data"""
        return self.client.get(url,
                               content_type='application/json',
                               headers=[('Accept', 'application/json')],
                               follow_redirects=follow_redirects)

    def json_post(self, url, data, follow_redirects=False):
        """Post json data"""
        return self.client.post(url,
                                data=json.dumps(data),
                                content_type='application/json',
                                headers=[('Accept', 'application/json')],
                                follow_redirects=follow_redirects)

    def json_put(self, url, data, follow_redirects=False):
        """Put json data"""
        return self.client.put(url,
                               data=json.dumps(data),
                               content_type='application/json',
                               headers=[('Accept', 'application/json')],
                               follow_redirects=follow_redirects)

    def json_delete(self, url, data=None, follow_redirects=False):
        """Delete request"""
        return self.client.delete(url,
                                  data=json.dumps(data),
                                  content_type='application/json',
                                  headers=[('Accept', 'application/json')],
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
                                                id=m.id)).data.decode('utf-8')) == dict(m)

    def test_jsonencoder_encodes_datetime(self):
        """Test that _JSONEncoder is used by asserting it's converting datetime
        objects"""
        m = SimpleModel(u'name')
        now = datetime.datetime.now()
        m.created = now
        self.session.add(m)
        self.session.flush()
        expected = dict(m)
        expected['created'] = expected['created'].isoformat()
        assert json.loads(self.json_get(url_for('SimpleModelView:get',
                                                id=m.id)).data.decode('utf-8')) == expected

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
        assert model.asdict(exclude=['created']) == {u'name': u'a name',
                                                     u'id': model_id}

    def test_post_with_missing_data(self):
        response = self.json_post(url_for('SimpleModelView:post'), {})
        assert response.status_code == 400
        assert u'name' in json.loads(response.data.decode('utf-8'))['errors']

    def test_put(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        model_id = m.id
        response = self.json_put(url_for('SimpleModelView:put', id=model_id),
                                 {'name': 'new name'})
        self.assert_redirects(response, response.location)
        m = self.session.query(SimpleModel).get(model_id)
        assert m.asdict(exclude=['created']) == {u'name': u'new name',
                                                 u'id': model_id}

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
        assert response.status_code == 200
        m = self.session.query(SimpleModel).get(model_id)
        assert not m

    def get_with_limit(self, limit):
        for i in range(100):
            m = SimpleModel(u'name %d' % i)
            self.session.add(m)
            self.session.flush()
        return self.json_get(url_for('SimpleModelView:index', limit=limit))

    def test_list_limit(self):
        response = self.get_with_limit(5)
        assert response.status_code == 200
        assert len(json.loads(response.data.decode('utf-8'))['items']) == 5

    def test_list_limit_greater_than_max(self):
        response = self.get_with_limit(1000)
        assert response.status_code == 200
        assert len(json.loads(response.data.decode('utf-8'))['items']) == 20

    def test_offset(self):
        self.session.query(SimpleModel).delete()
        for i in range(20):
            m = SimpleModel(u'name %d' % i)
            m.id = i + 1
            self.session.add(m)
            self.session.flush()
        response = self.json_get(url_for('SimpleModelView:index',
                                         sortby='id',
                                         offset=10))
        assert response.status_code == 200
        assert json.loads(response.data.decode('utf-8'))['items'][0]['id'] == 11

    def test_get_html(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        response = self.client.get(url_for('SimpleModelView:get',
                                           id=m.id))
        assert 'ITEM_ID=%d' % m.id in response.data.decode('utf-8')

    def test_get_invalid_id_html(self):
        response = self.client.get(url_for('SimpleModelView:get',
                                           id=u'a string'))
        assert response.status_code == 404
        assert 'DOCTYPE HTML' in response.data.decode('utf-8')
        assert '404 Not Found' in response.data.decode('utf-8')

    def test_invalid_offset_html(self):
        response = self.client.get(url_for('SimpleModelView:index',
                                           sortby='id',
                                           offset='invalid'))
        assert response.status_code == 400
        assert 'DOCTYPE HTML' in response.data.decode('utf-8')
        assert 'Bad Request' in response.data.decode('utf-8')

    def test_missing_template_generates_406(self):
        response = self.client.get(url_for('SimpleModelView:index'))
        assert response.status_code == 406

    def test_before_render_get(self):
        before_data = 'test_before_render_get'

        def fn(self, data):
            return {'before_data': before_data}

        setattr(SimpleModelView, 'before_get_render', fn)
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        response = self.client.get(url_for('SimpleModelView:get', id=m.id))
        assert before_data in response.data.decode('utf-8')
        delattr(SimpleModelView, 'before_get_render')

    def test_put_missing_data_not_accept_json(self):
        m = SimpleModel(u'name')
        self.session.add(m)
        self.session.flush()
        model_id = m.id
        response = self.client.put(
            url_for('SimpleModelView:put',
                    id=model_id),
            data=json.dumps({'fakekey': 'new name'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

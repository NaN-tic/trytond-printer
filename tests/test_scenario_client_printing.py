import base64
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from proteus import Model
from trytond.modules.printer import printer
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules
from trytond.wsgi import app
from werkzeug.test import Client
from werkzeug.wrappers import Response


class TestClientPrinting(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('printer')
        User = Model.get('res.user', config=config)
        user = User(name='Print User', login='print-user',
            password='printer-test-password')
        user.save()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        message = '{"call":"printers.find","timestamp":1234567890}'
        route = '/%s/printer/sign_message' % config.database_name
        rpc = '/%s/rpc/' % config.database_name
        payload = {'id': 1, 'method': 'model.printer.sign_message',
            'params': [message, {}]}
        client = Client(app, Response)

        with (patch.object(printer, 'PRIVATE_KEY', private_key),
                patch.object(printer, 'PRIVATE_KEY_PASS', None)):
            self.assertEqual(client.post(
                route, json={'request': message}).status_code, 401)
            self.assertEqual(client.post(rpc, json=payload).status_code, 401)

            login = client.post(rpc, json={
                'id': 2, 'method': 'common.db.login',
                'params': [user.login, {'password': 'printer-test-password'}]})
            self.assertEqual(login.status_code, 200)
            user_id, token, _ = login.json['result']
            authorization = 'Session ' + base64.b64encode(
                ('%s:%s:%s' % (user.login, user_id, token)).encode()).decode()
            headers = {'Authorization': authorization}
            response = client.post(rpc, json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)
            signature = response.json['result']
            key.public_key().verify(base64.b64decode(signature),
                message.encode(), padding.PKCS1v15(), hashes.SHA512())
            response = client.post(route, json={'request': message},
                headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, signature)

            invalid = {'Authorization': 'Session ' + base64.b64encode(
                ('%s:%s:invalid' % (user.login, user_id)).encode()).decode()}
            self.assertEqual(client.post(
                route, json={'request': message},
                headers=invalid).status_code, 401)
            self.assertEqual(client.post(
                rpc, json=payload, headers=invalid).status_code, 401)

            # Cassini sends the standard Tryton cookie with its signing request.
            cookie_client = Client(app, Response)
            response = cookie_client.post(
                '/%s/session/login' % config.database_name,
                json={'params': [user.login,
                        {'password': 'printer-test-password'}]})
            self.assertEqual(response.status_code, 200)
            response = cookie_client.post(route, json={'request': message})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, signature)
            response = cookie_client.post(
                '/%s/session/logout' % config.database_name)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(cookie_client.post(
                route, json={'request': message}).status_code, 401)

            response = client.post(rpc, headers=headers, json={
                'id': 3, 'method': 'common.db.logout', 'params': []})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.post(route, headers=headers,
                json={'request': message}).status_code, 401)
            self.assertEqual(client.post(rpc, headers=headers,
                json=payload).status_code, 401)

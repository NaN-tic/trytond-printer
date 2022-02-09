# This file is part of Tryton. The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import base64
import logging
import json
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from werkzeug.wrappers import Response

from trytond.config import config
from trytond.wsgi import app
from trytond.protocols.wrappers import with_pool, with_transaction

logger = logging.getLogger(__name__)

PRIVATE_KEY = config.get('printer', 'private_key')
PRIVATE_KEY_PASS = config.get('printer', 'private_key_pass',
    default=None)


@app.route('/<database_name>/printer/sign_message', methods=['POST'])
@with_pool
@with_transaction()
def sign_message(request, pool):
    request_body = request.get_data(as_text=True)
    data = json.loads(request_body)
    message = data.get('request', None)

    if not message or not PRIVATE_KEY:
        logger.info("No Private Key deffined or in the request is "
            "missing the message")
        return Response('', 200, content_type="text/plain")

    mypass = (PRIVATE_KEY_PASS.encode('utf-8')
        if PRIVATE_KEY_PASS else None)
    # Load signature
    key = serialization.load_pem_private_key(PRIVATE_KEY.encode(
            'utf-8'), mypass, backend=default_backend())
    # Create the signature
    signature = key.sign(message.encode('utf-8'), padding.PKCS1v15(),
        hashes.SHA512())
    # Echo the signature
    return Response(base64.b64encode(signature), 200,
        content_type="text/plain")

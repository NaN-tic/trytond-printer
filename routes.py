# This file is part of Tryton. The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import json

from werkzeug.wrappers import Response

from trytond.wsgi import app
from trytond.protocols.wrappers import with_pool, with_transaction


@app.route('/<database_name>/printer/sign_message', methods=['POST'])
@app.auth_required
@with_pool
@with_transaction(readonly=True, user='request')
def sign_message(request, pool):
    Printer = pool.get('printer')
    data = json.loads(request.get_data(as_text=True))
    return Response(Printer.sign_message(data.get('request')), 200,
        content_type="text/plain")

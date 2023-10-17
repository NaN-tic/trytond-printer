
from trytond.pool import PoolMeta
from trytond.model import fields

class User(metaclass=PoolMeta):
    __name__ = 'res.user'

    ignore_printer_rules = fields.Boolean('Ignore Printer Rules')

    @classmethod
    def __setup__(cls):
        super(User, cls).__setup__()
        cls._preferences_fields.extend(['ignore_printer_rules'])
        cls._context_fields.insert(0, 'ignore_printer_rules')
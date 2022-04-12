import os
import cups
import tempfile
import ipaddress
import subprocess
from datetime import datetime
from trytond.model import (sequence_ordered, ModelSQL, ModelView, MatchMixin,
    fields)
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError

__all__ = ['Printer', 'PrinterRule', 'PrinterState', 'RuleState', 'Cron']

PRINTER_STATES = [
    ('unavailable', 'Unavailable'),
    ('printing', 'Printing'),
    ('unknown', 'Unknown'),
    ('available', 'Available'),
    ('error', 'Error'),
    ('server-error', 'Server Error'),
    ]

STATE_MAPPING = {
    3: 'available',
    4: 'printing',
    5: 'error'
    }


class Cron(metaclass=PoolMeta):
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super(Cron, cls).__setup__()
        cls.method.selection.extend(
            [('printer|cron_update_info', 'Update Printer Information')])


class Printer(ModelSQL, ModelView):
    'Printer'
    __name__ = 'printer'

    name = fields.Char('Name', required=True)
    system_name = fields.Char('System Name', required=True, readonly=True)
    state = fields.Function(fields.Selection(PRINTER_STATES, 'State'),
        'get_state')
    model = fields.Char('Model', readonly=True)
    location = fields.Char('Location', readonly=True)
    uri = fields.Char('URI', readonly=True)
    orientation = fields.Selection([
            ('0', 'No rotation'),
            ('90', 'Rotate 90 degrees'),
            ('180', 'Rotate 180 degrees'),
            ('270', 'Rotate 270 degrees'),
            ], 'Orientation', required=True, sort=False)
    last_update = fields.DateTime('Last Update', required=True, readonly=True)

    @staticmethod
    def default_state():
        return 'unknown'

    @staticmethod
    def default_orientation():
        return '0'

    @classmethod
    def __setup__(cls):
        super(Printer, cls).__setup__()
        cls._buttons.update({
                'update_info': {
                    'icon': 'tryton-refresh',
                    },
                'test': {
                    'icon': 'tryton-print',
                    }
                })

    def get_rec_name(self, name):
        return '%s (%s)' % (self.name, self.state)

    @classmethod
    def get_state(cls, printers, name):
        try:
            connection = cls.cups_connection()
            cups_printers = connection.getPrinters()
            server_error = False
        except:
            server_error = True
        res = {}
        for printer in printers:
            if server_error:
                res[printer.id] = 'server-error'
            elif printer.system_name in cups_printers:
                info = cups_printers[printer.system_name]
                res[printer.id] = STATE_MAPPING.get(info['printer-state'],
                    'unknown')
            else:
                res[printer.id] = 'unavailable'
        return res

    @classmethod
    def cron_update_info(cls):
        cls.update_info([])

    @staticmethod
    def path():
        return os.path.abspath(os.path.dirname(__file__))

    @staticmethod
    def cups_connection():
        return cups.Connection()

    @classmethod
    @ModelView.button
    def test(cls, printers):
        connection = cls.cups_connection()
        for printer in printers:
            connection.printTestPage(printer.system_name)

    @classmethod
    @ModelView.button
    def update_info(cls, printers):
        try:
            connection = cls.cups_connection()
            cups_printers = connection.getPrinters()
            server_error = False
        except:
            server_error = True

        to_save = []
        for printer in cls.search([]):
            if printer.system_name in cups_printers:
                info = cups_printers.pop(printer.system_name)
                printer.last_update = datetime.now()
                printer.model = info.get('printer-make-and-model')
                printer.location = info.get('printer-location')
                printer.uri = info.get('printer-uri-supported')
            to_save.append(printer)
        if not printers and not server_error:
            for system_name, info in cups_printers.items():
                printer = cls()
                printer.name = system_name
                printer.system_name = system_name
                printer.last_update = datetime.now()
                printer.model = info.get('printer-make-and-model')
                printer.location = info.get('printer-location')
                printer.uri = info.get('printer-uri-supported')
                to_save.append(printer)
        if to_save:
            cls.save(to_save)

    @classmethod
    def send_report(cls, type, data, name, report):
        pool = Pool()
        Rule = pool.get('printer.rule')
        User = pool.get('res.user')

        pattern = {}
        user_id = Transaction().user
        if user_id:
            user = User(user_id)
            pattern['user'] = user.id
            pattern['groups'] = [x.id for x in user.groups]
        if report:
            pattern['report'] = report.id
        context = Transaction().context
        remote_addr = context.get('_request', {}).get('remote_addr')
        if remote_addr:
            pattern['ip_address'] = ipaddress.ip_address(remote_addr)

        action = None
        client_direct_print = report.direct_print if report else False
        printer = None
        client_printer = None
        for rule in Rule.search([]):
            if rule.match(pattern):
                if rule.action and not action:
                    action = rule.action
                    client_direct_print = rule.client_direct_print
                if rule.printer and not printer:
                    printer = rule.printer
                if rule.client_printer and not client_printer:
                    client_printer = rule.client_printer
                if action:
                    if action == 'drop':
                        break
                    elif action == 'server' and printer:
                        break
                    elif action == 'client' and client_printer:
                        break
        if not action or action == 'client':
            return type, data, client_direct_print, client_printer or name
        elif action == 'drop':
            return
        elif action == 'server':
            if not printer:
                raise UserError(gettext('printer.no_printer'))
            printer.print_data(data, name)

    def print_data(self, data, name):
        fd, filename = tempfile.mkstemp()
        try:
            os.close(fd)
            with open(filename, 'wb') as f:
                f.write(data)
            self.print_file(filename, name)
        finally:
            os.unlink(filename)

    def print_file(self, filename, name):
        rotated_filename = None
        try:
            if self.orientation != '0':
                fd, rotated_filename = tempfile.mkstemp()
                os.close(fd)
                if self.orientation == '90':
                    rotation = 'east'
                elif self.orientation == '180':
                    rotation = 'south'
                else:
                    rotation = 'west'
                process = subprocess.Popen(['/usr/bin/pdftk', filename, 'cat',
                        '1-end%s' % rotation, 'output', rotated_filename],
                    close_fds=True)
                process.wait()
                filename = rotated_filename

            connection = self.cups_connection()
            connection.printFile(self.system_name, filename, name, {})
        finally:
            if rotated_filename:
                os.unlink(rotated_filename)


class PrinterRule(sequence_ordered(), ModelSQL, ModelView, MatchMixin):
    'Printer Rule'
    __name__ = 'printer.rule'

    user = fields.Many2One('res.user', 'User')
    group = fields.Many2One('res.group', 'Group')
    report = fields.Many2One('ir.action.report', 'Report')
    ip_address = fields.Char('IP Address or Network', help='IPv4 or IPv6 IP '
        'address or network. Valid values include: 192.168.0.26 or '
        '192.168.0.0/24')
    action = fields.Selection([
            (None, ''),
            ('drop', 'Drop'),
            ('server', 'Send to Printer'),
            ('client', 'Send to Client'),
            ], 'Action')
    client_direct_print = fields.Boolean('Client Direct Print', states={
            'invisible': Eval('action') != 'client',
            })
    printer = fields.Many2One('printer', 'Printer', states={
            'invisible': Eval('action') == 'client',
            })
    client_printer = fields.Char('Client Printer', states={
            'invisible': Eval('action') != 'client',
            })
    printer_states = fields.Many2Many('printer.rule.state', 'rule', 'state',
        'Printer States', states={
            'invisible': ~Eval('printer') | (Eval('action') == 'client'),
            })
    printer_states_char = fields.Function(fields.Char('Printer States',
            states={
                'invisible': ~Eval('printer') | (Eval('action') == 'client'),
                }),
        'get_printer_states_char')

    @classmethod
    def validate(cls, rules):
        for rule in rules:
            rule.check_ip()

    def check_ip(self):
        if not self.ip_address:
            return
        try:
            if '/' in self.ip_address:
                ipaddress.ip_network(self.ip_address)
            else:
                ipaddress.ip_address(self.ip_address)
        except ValueError:
            raise UserError(gettext('printer.invalid_ip_address',
                    ip=self.ip_address,
                    rule=self.rec_name))

    def get_ip_network(self):
        if not self.ip_address:
            return
        if '/' in self.ip_address:
            return ipaddress.ip_network(self.ip_address)

    def get_ip_address(self):
        if not self.ip_address:
            return
        if '/' not in self.ip_address:
            return ipaddress.ip_address(self.ip_address)

    def match(self, pattern):
        if 'groups' in pattern:
            pattern = pattern.copy()
            groups = pattern.pop('groups')
            if self.group and self.group.id not in groups:
                return False
        if 'ip_address' in pattern:
            ip_address = ipaddress.ip_address(pattern['ip_address'])
            if (self.get_ip_network()
                    and ip_address not in self.get_ip_network()):
                return False
            if (self.get_ip_address() and ip_address != self.get_ip_address()):
                return False

        res = super(PrinterRule, self).match(pattern)
        if res and self.printer and self.printer_states:
            if (self.printer.state and self.printer.state not in [
                        x.system_name for x in self.printer_states]):
                return False
        return res

    def get_printer_states_char(self, name):
        return ', '.join([x.name for x in self.printer_states])


class PrinterState(ModelSQL, ModelView):
    'Printer State'
    __name__ = 'printer.state'

    name = fields.Char('Name', required=True, translate=True)
    system_name = fields.Char('System Name', required=True)

    @classmethod
    def __setup__(cls):
        super(PrinterState, cls).__setup__()
        cls._order.insert(0, ('name', 'ASC'))


class RuleState(ModelSQL):
    'Rule - State'
    __name__ = 'printer.rule.state'

    rule = fields.Many2One('printer.rule', 'Rule', required=True,
        ondelete='CASCADE')
    state = fields.Many2One('printer.state', 'State', required=True,
        ondelete='CASCADE')

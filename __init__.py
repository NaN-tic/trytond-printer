# This file is part printer module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import printer
from . import routes
from . import user

__all__ = ['register', 'routes']


def register():
    Pool.register(
        printer.Printer,
        printer.PrinterRule,
        printer.PrinterState,
        printer.RuleState,
        printer.Cron,
        user.User,
        module='printer', type_='model')

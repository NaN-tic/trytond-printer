Printer Module
##############

The printer module allows administrators to define rules to decide if reports
are sent to the client, sent to a specific printer or dropped.

The module connects to a local CUPS [1] server and obtains all available
printers creating them as a 'printer' record.

Currently, rules are only applied to jasper reports (use the jasper_reports
module) and you should add this to your trytond.conf:

[jasper]
redirect_model = printer


[1] http://www.cups.org

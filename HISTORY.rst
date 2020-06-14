=======
History
=======

0.1.0 (2019-07-01)
------------------

* First release on PyPI.

p = myInactiveWidget.palette();
for colorRole in range(QPalette.NColorRoles):
    p.setColor(QPalette.Inactive, colorRole, p.color(QPalette.Active, colorRole));
myInactiveWidget.setPalette(p);

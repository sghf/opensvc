#
# Copyright (c) 2011 Christophe Varoqui <christophe.varoqui@opensvc.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
import checks
from rcUtilities import justcall

class check(checks.check):
    chk_type = "mpath"

    def find_svc(self, dev):
        for svc in self.svcs:
            if dev in svc.disklist():
                return svc.svcname
        return ''

    def odmget(self, lname, attr):
        cmd = ['odmget', '-q', 'name='+lname+' AND attribute='+attr, 'CuAt']
        out, err, ret = justcall(cmd)
        for f in out.split('\n'):
            if "value" not in f:
                continue
            return f.split(" = ")[-1].strip('"')
        return None

    def disk_id(self, dev):
        return self.odmget(dev, 'wwid')

    def do_check(self):
        cmd = ['lspath']
        out, err, ret = justcall(cmd)
        if ret != 0:
            return self.undef
        lines = out.split('\n')
        if len(lines) < 1:
            return self.undef
        r = []
        dev = None
        wwid = None
        for line in lines:
            l = line.split()
            if len(l) != 3:
                continue
            if l[0] != 'Enabled':
                continue
            if dev is None:
                dev = l[1]
                wwid = self.disk_id(dev)
                n = 1
            elif dev is not None and wwid is not None and dev != l[1]:
                r.append({'chk_instance': wwid,
                          'chk_value': str(n),
                          'chk_svcname': self.find_svc(dev),
                         })
                dev = l[1]
                wwid = self.disk_id(dev)
                n = 1
            else:
                n += 1
        if dev is not None and wwid is not None:
            r.append({'chk_instance': wwid,
                      'chk_value': str(n),
                      'chk_svcname': self.find_svc(dev),
                     })
        return r

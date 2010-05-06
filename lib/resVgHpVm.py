#
# Copyright (c) 2009 Christophe Varoqui <christophe.varoqui@free.fr>'
# Copyright (c) 2009 Cyril Galibern <cyril.galibern@free.fr>'
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
import re
import os
import rcExceptions as ex
import rcStatus
resVg = __import__("resVgHP-UX")
from subprocess import *
from rcUtilities import qcall
from rcGlobalEnv import rcEnv
from subprocess import *

class Vg(resVg.Vg):
    def __init__(self, rid=None, name=None, type=None,
                 optional=False, disabled=False):
        self.label = name
        resVg.Vg.__init__(self, rid=rid, name=name,
                          type='disk.vg',
                          optional=optional, disabled=disabled)

    def has_it(self):
        return True

    def is_up(self):
        return True

    def status(self, verbose=False):
        return rcStatus.NA

    def do_start(self):
        self.do_mksf()

    def do_stop(self):
        pass

    def diskupdate(self):
        if self.svc.status() != 0:
            self.do_mksf()
            self.do_share()
        else:
            self.write_mksf()
            self.write_share()

    def sharefile_name(self):
        return os.path.join(rcEnv.pathvar, 'vg_' + self.svc.svcname + '_' + self.name + '.share')

    def write_share(self):
        cmd = ['/opt/hpvm/bin/hpvmdevmgmt', '-l', 'all:DEVTYPE=DISK']
        (ret, buff) = self.call(cmd)
        if ret != 0:
            raise ex.excError
        if len(buff) == 0:
            return
        disklist = self.disklist()
        with open(self.sharefile_name(), 'w') as f:
            for line in buff.split('\n'):
                dev = line.split(':')[0]
                if len(dev) == 0:
                    continue
                if dev not in disklist:
                    continue
                if 'SHARE=YES' in line:
                    f.write(dev+':YES\n')
                else:
                    f.write(dev+':NO\n')

    def do_share(self):
        if not os.path.exists(self.sharefile_name()):
            return
        cmd = ['/opt/hpvm/bin/hpvmdevmgmt', '-l', 'all:DEVTYPE=DISK']
        (ret, buff) = self.call(cmd)
        if ret != 0:
            raise ex.excError
        devs = set([])
        for line in buff.split('\n'):
            l = line.split(':')
            if len(l) == 0:
                continue
            if len(l[0]) == 0:
                continue
            devs |= set([l[0]])
        with open(self.sharefile_name(), 'r') as f:
            err = 0
            for line in f.readlines():
                l = line.split(':')
                if len(l) != 2:
                    continue
                dev = l[0]
                if len(dev) == 0:
                    continue
                if not os.path.exists(dev):
                    continue
                if dev not in devs:
                    cmd = ['/opt/hpvm/bin/hpvmdevmgmt', '-a', 'gdev:'+dev]
                    (ret, out) = self.vcall(cmd)
                    if ret != 0:
                        raise ex.excError
                if 'YES' in l[1]:
                    cmd = ['/opt/hpvm/bin/hpvmdevmgmt', '-m', 'gdev:'+dev+':attr:SHARE=YES']
                else:
                    cmd = ['/opt/hpvm/bin/hpvmdevmgmt', '-m', 'gdev:'+dev+':attr:SHARE=NO']
                (ret, buff) = self.vcall(cmd)
                if ret != 0:
                    err += 1
                    continue
        if err > 0:
            raise ex.excError

    def disklist(self):
        cmd = ['/opt/hpvm/bin/hpvmstatus', '-d', '-P', self.svc.vmname]
        p = Popen(cmd, stdout=PIPE, stderr=PIPE, close_fds=True)
        buff = p.communicate()
        if p.returncode != 0:
            raise ex.excError

        for line in buff[0].split('\n'):
            l = line.split(':')
            if len(l) < 5:
                continue
            if l[3] != 'disk':
                continue
            self.disks |= set([l[4]])
        return self.disks

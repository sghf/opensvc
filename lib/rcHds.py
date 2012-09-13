from rcUtilities import which, justcall
import rcExceptions as ex
import os
import ConfigParser

pathlib = os.path.dirname(__file__)
pathbin = os.path.realpath(os.path.join(pathlib, '..', 'bin'))
pathetc = os.path.realpath(os.path.join(pathlib, '..', 'etc'))
pathtmp = os.path.realpath(os.path.join(pathlib, '..', 'tmp'))

def _cmd(cmd, url, username, password, serial):
    bin = "HiCommandCLI"
    if which(bin) is None:
        print "Can not find %s"%bin
        raise ex.excError
    l = [bin, url, cmd[0],
         "-u", username,
         "-p", password,
         "serialnum="+serial]
    if len(cmd) > 1:
        l += cmd[1:]
    #print ' '.join(l)
    out, err, ret = justcall(l)
    #print out, err, ret
    if ret != 0:
        raise ex.excError(err)
    return out, err, ret

class Hdss(object):
    arrays = []
    def __init__(self, objects=[]):
        self.objects = objects
        if len(objects) > 0:
            self.filtering = True
        else:
            self.filtering = False
        self.index = 0

        cf = os.path.join(pathetc, "auth.conf")
        if not os.path.exists(cf):
            return
        conf = ConfigParser.RawConfigParser()
        conf.read(cf)
        m = []
        for s in conf.sections():
            try:
                stype = conf.get(s, 'type')
            except:
                continue
            if stype != "hds":
                continue
            try:
                url = conf.get(s, 'url')
                arrays = conf.get(s, 'array').split()
                username = conf.get(s, 'username')
                password = conf.get(s, 'password')
                m += [(url, arrays, username, password)]
            except:
                print "error parsing section", s
                pass
        del(conf)
        done = []
        for url, arrays, username, password in m:
            for name in arrays:
                if self.filtering and name not in self.objects:
                    continue
                if name in done:
                    continue
                self.arrays.append(Hds(name, url, username, password))
                done.append(name)

    def __iter__(self):
        return self

    def next(self):
        if self.index == len(self.arrays):
            raise StopIteration
        self.index += 1
        return self.arrays[self.index-1]

class Hds(object):
    def __init__(self, serial, url, username, password):
        self.keys = ['lu', 'arraygroup']
        self.name = serial
        self.serial = serial
        self.url = url
        self.username = username
        self.password = password

    def _cmd(self, cmd):
        return _cmd(cmd, self.url, self.username, self.password, self.serial)

    def get_lu(self):
        cmd = ['GetStorageArray', 'subtarget=Logicalunit', 'lusubinfo=Path,LDEV,VolumeConnection']
        print ' '.join(cmd)
        out, err, ret = self._cmd(cmd)
        return out

    def get_arraygroup(self):
        cmd = ['GetStorageArray', 'subtarget=ArrayGroup']
        print ' '.join(cmd)
        out, err, ret = self._cmd(cmd)
        return out

if __name__ == "__main__":
    o = Hdss()
    for hds in o:
        print hds.lu()


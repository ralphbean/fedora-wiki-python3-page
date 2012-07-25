from collections import namedtuple
import cStringIO
import difflib
import os
from pprint import pprint
import re
import subprocess
import sys
import urllib2

from BeautifulSoup import BeautifulSoup

def get_mw():
    # Get the MediaWiki source (plus some HTML textarea markup) for the
    # "Python 3 already in Fedora" section of the wiki page
    # (section 2 is the one we want)
    URL = 'https://fedoraproject.org/w/index.php?title=Python3&action=edit&section=2'

    f = urllib2.urlopen(URL)
    html = f.read()

    soup = BeautifulSoup(html)
    # print(soup.prettify())

    lines = soup('textarea')
    return str(lines[0])

class PackageLine:
    ATTRNAMES = ('pymodule', 'fedpy2', 'upstream', 'fedpy3')
    def __init__(self, pymodule, fedpy2, upstream, fedpy3):
        self.pymodule = pymodule
        self.fedpy2 = fedpy2
        self.upstream = upstream
        self.fedpy3 = fedpy3

    def write_mw(self, f):
        f.write('|-\n')
        columns = []
        for attrname in self.ATTRNAMES:
            field = getattr(self, attrname)
            if field == '':
                field = ' '
            else:
                field = ' %s ' % field
            columns.append(field)
        f.write('|' + ('||'.join(columns)).rstrip() + '\n')

    def __cmp__(self, other):
        for attrname in self.ATTRNAMES:
            j = cmp(getattr(self, attrname).lower(),
                    getattr(other, attrname).lower())
            if j: return j
        return 0

class PackageTable:
    def __init__(self, text):
        self.packages = []
        state = []
        for line in text.splitlines():
            if line.startswith('|') and not line.startswith('|-') \
                    and not line.startswith('|}'):
                if 0:
                    print('line: %r' % line)
                fields = line[1:].split('||')
                if len(fields) == 3:
                    fields.append('')
                fields = [field.strip() for field in fields]
                p = PackageLine(*fields)
                self.packages.append(p)

    def sort(self):
        def sorter(a, b):
            return cmp(a, b)
        self.packages.sort(sorter)

    def write_mw(self, f):
        f.write('== Python 3 already in Fedora ==\n')
        f.write('{|\n')
        f.write('! Python Module !! Fedora Python 2 package !! Upstream status of Python 3 !! Fedora Python 3 package\n')
        for pkg in self.packages:
            pkg.write_mw(f)
        f.write('|}')

    def add_srpm(self, srpmname, subpackages):
        for package in self.packages:
            if srpmname == package.fedpy2 or \
                    srpmname in package.fedpy3:
                # already in table;
                return
        # Generating the modules list is the slow part:
        pymodule = ' '.join(sorted(get_modules_for_subpackages(subpackages)))
        fedpy2 = ''
        upstream = ''
        names = ' '.join(["'''%s'''" % name
                          for name in sorted(subpackages)])
        if len(subpackages) > 1:
            fedpy3 = ("In Fedora as subpackages %s of %s"
                      % (names, srpmname))
        else:
            fedpy3 = ("In Fedora as %s subpackage of %s"
                      % (names, srpmname))
        newline = PackageLine(pymodule, fedpy2, upstream, fedpy3)
        self.packages.append(newline)

def parse_table(text):
    return PackageTable(text)

def get_modules_for_subpackages(subpackages):
    result = set()
    for subpackage in subpackages:
        result = result.union(get_modules(subpackage))
    for pkg in list(result):
        if pkg.startswith('_') and pkg[1:] in result:
            result.discard(pkg)
    return result

def get_modules(subpackage):
    specialcases = {'dreampie-python3': 'dreampielib',
                    'nose': 'nose',
                    'python3-nose1.1': 'nose',
                    'waf-python3': 'waflib',
                    'znc-modpython': 'znc',
                    }
    if subpackage in specialcases:
        return set([specialcases[subpackage]])
    cmd = ['repoquery',
           '--list', subpackage]
    result = set()
    print('subpackage: %r' % subpackage)
    for line in subprocess.check_output(cmd).splitlines():
        if 1:
            print('line: %r' % line)
        dirname, basename = os.path.split(line)
        if dirname.endswith('site-packages'):
            if basename == '__pycache__':
                continue
            if basename.endswith('egg-info'):
                continue
            if basename.endswith('.egg'):
                continue
            if basename.endswith('.pth'):
                continue

            m = re.match('(.+).cpython-(.+).so', basename)
            if m:
                result.add(m.group(1))
                continue

            if basename.endswith('.py'):
                result.add(basename[:-3])
            elif basename.endswith('.pyc'):
                result.add(basename[:-4])
            elif basename.endswith('.pyo'):
                result.add(basename[:-4])
            else:
                result.add(basename)
    return result

def get_srpms():
    # Get srpms that build something requiring python3
    # Returns a dict, mapping from srpm names to sets of subpackage names
    # requiring python3
    #  e.g. {'mpi4py': set(['python3-mpi4py-mpich2',
    #                       'python3-mpi4py-openmpi']),
    #        'numpy': set(['python3-numpy', 'python3-numpy-f2py']),
    #        ...etc...
    #        }
    result = {}
    cmd = ['repoquery',
           '--qf', '%{sourcerpm} %{name}',
           '--whatrequires', 'python3']
    for line in subprocess.check_output(cmd).splitlines():

        sourcerpm, subpackagename = line.split()
        # e.g. 'cobbler-2.2.2-1.fc17.src.rpm', 'cobbler-web'

        srpmname = re.match('(.+)-(.+)-(.+)', sourcerpm).group(1)
        if srpmname in result:
            result[srpmname].add(subpackagename)
        else:
            result[srpmname] = set([subpackagename])
    return result

if 1:
    oldcontent = get_mw()
    table = parse_table(oldcontent)

    if 1:
        for srpmname, subpackages in get_srpms().iteritems():
            table.add_srpm(srpmname, subpackages)

    table.sort()

    #pprint(table.lines)
    newcontent = cStringIO.StringIO()
    table.write_mw(newcontent)
    newcontent = newcontent.getvalue()

    def unified_diff(oldtxt, newtxt):
        def _make_lines(text):
            return [line + '\n' for line in text.splitlines()]
        diff = difflib.unified_diff(_make_lines(oldtxt),
                                    _make_lines(newtxt))
        return ''.join(diff)

    # Show diff between old and proposed new content:
    print(unified_diff(oldcontent, newcontent))

    # Show new content, for ease of pasting into the edit textarea:
    print(newcontent)


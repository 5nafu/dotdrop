"""
author: deadc0de6 (https://github.com/deadc0de6)
Copyright (c) 2017, deadc0de6

handle the update of dotfiles
"""

import os
import shutil
import filecmp

# local imports
from dotdrop.logger import Logger
from dotdrop.templategen import Templategen
import dotdrop.utils as utils


TILD = '~'


class Updater:

    def __init__(self, conf, dotpath, profile, variables, dry, safe,
                 iskey=False, debug=False, ignore=[], showpatch=False):
        """constructor
        @conf: configuration
        @dotpath: path where dotfiles are stored
        @profile: profile selected
        @variables: dictionary of variables for the templates
        @dry: simulate
        @safe: ask for overwrite if True
        @iskey: will the update be called on keys or path
        @debug: enable debug
        @ignore: pattern to ignore when updating
        @showpatch: show patch if dotfile to update is a template
        """
        self.conf = conf
        self.dotpath = dotpath
        self.profile = profile
        self.variables = variables
        self.dry = dry
        self.safe = safe
        self.iskey = iskey
        self.debug = debug
        self.ignore = ignore
        self.showpatch = showpatch
        self.log = Logger()

    def update_path(self, path):
        """update the dotfile installed on path"""
        if not os.path.lexists(path):
            self.log.err('\"{}\" does not exist!'.format(path))
            return False
        path = self._normalize(path)
        dotfile = self._get_dotfile_by_path(path)
        if not dotfile:
            return False
        path = os.path.expanduser(path)
        if self.debug:
            self.log.dbg('updating {} from path \"{}\"'.format(dotfile, path))
        return self._update(path, dotfile)

    def update_key(self, key):
        """update the dotfile referenced by key"""
        dotfile = self._get_dotfile_by_key(key)
        if not dotfile:
            return False
        if self.debug:
            self.log.dbg('updating {} from key \"{}\"'.format(dotfile, key))
        path = self._normalize(dotfile.dst)
        return self._update(path, dotfile)

    def _update(self, path, dotfile):
        """update dotfile from file pointed by path"""
        ret = False
        new_path = None
        self.ignores = list(set(self.ignore + dotfile.upignore))
        if self.debug:
            self.log.dbg('ignore pattern(s): {}'.format(self.ignores))

        left = os.path.expanduser(path)
        right = os.path.join(self.conf.abs_or_rel(self.dotpath), dotfile.src)
        right = os.path.expanduser(right)

        if self._ignore([left, right]):
            return True
        if dotfile.trans_w:
            # apply write transformation if any
            new_path = self._apply_trans_w(path, dotfile)
            if not new_path:
                return False
            left = new_path
        if os.path.isdir(left):
            ret = self._handle_dir(left, right)
        else:
            ret = self._handle_file(left, right)
        # clean temporary files
        if new_path and os.path.exists(new_path):
            utils.remove(new_path)
        return ret

    def _apply_trans_w(self, path, dotfile):
        """apply write transformation to dotfile"""
        trans = dotfile.trans_w
        if self.debug:
            self.log.dbg('executing write transformation {}'.format(trans))
        tmp = utils.get_unique_tmp_name()
        if not trans.transform(path, tmp):
            msg = 'transformation \"{}\" failed for {}'
            self.log.err(msg.format(trans.key, dotfile.key))
            if os.path.exists(tmp):
                utils.remove(tmp)
            return None
        return tmp

    def _normalize(self, path):
        """normalize the path to match dotfile"""
        path = os.path.expanduser(path)
        path = os.path.expandvars(path)
        path = os.path.abspath(path)
        home = os.path.expanduser(TILD) + os.sep

        # normalize the path
        if path.startswith(home):
            path = path[len(home):]
            path = os.path.join(TILD, path)
        return path

    def _get_dotfile_by_key(self, key):
        """get the dotfile matching this key"""
        dotfiles = self.conf.get_dotfiles(self.profile)
        subs = [d for d in dotfiles if d.key == key]
        if not subs:
            self.log.err('key \"{}\" not found!'.format(key))
            return None
        if len(subs) > 1:
            found = ','.join([d.src for d in dotfiles])
            self.log.err('multiple dotfiles found: {}'.format(found))
            return None
        return subs[0]

    def _get_dotfile_by_path(self, path):
        """get the dotfile matching this path"""
        dotfiles = self.conf.get_dotfiles(self.profile)
        subs = [d for d in dotfiles if d.dst == path]
        if not subs:
            self.log.err('\"{}\" is not managed!'.format(path))
            return None
        if len(subs) > 1:
            found = ','.join([d.src for d in dotfiles])
            self.log.err('multiple dotfiles found: {}'.format(found))
            return None
        return subs[0]

    def _is_template(self, path):
        if not Templategen.is_template(path):
            return False
        self.log.warn('{} uses template, update manually'.format(path))
        return True

    def _show_patch(self, tpath, fpath):
        """provide a way to manually patch the template"""
        content = self._resolve_template(tpath)
        tmp = utils.write_to_tmpfile(content)
        cmds = ['diff', '-u', tmp, fpath, '|', 'patch', tpath]
        self.log.warn('try patching with: \"{}\"'.format(' '.join(cmds)))
        return False

    def _resolve_template(self, tpath):
        """resolve the template to a temporary file"""
        t = Templategen(variables=self.variables, base=self.dotpath,
                        debug=self.debug)
        return t.generate(tpath)

    def _handle_file(self, left, right, compare=True):
        """sync left (deployed file) and right (dotdrop dotfile)"""
        if self._ignore([left, right]):
            return True
        if self.debug:
            self.log.dbg('update for file {} and {}'.format(left, right))
        if self._is_template(right):
            # dotfile is a template
            if self.debug:
                self.log.dbg('{} is a template'.format(right))
            if self.showpatch:
                self._show_patch(right, left)
            return False
        if compare and filecmp.cmp(left, right, shallow=True):
            # no difference
            if self.debug:
                self.log.dbg('identical files: {} and {}'.format(left, right))
            return True
        if not self._overwrite(left, right):
            return False
        try:
            if self.dry:
                self.log.dry('would cp {} {}'.format(left, right))
            else:
                if self.debug:
                    self.log.dbg('cp {} {}'.format(left, right))
                shutil.copyfile(left, right)
        except IOError as e:
            self.log.warn('{} update failed, do manually: {}'.format(left, e))
            return False
        return True

    def _handle_dir(self, left, right):
        """sync left (deployed dir) and right (dotdrop dir)"""
        if self.debug:
            self.log.dbg('handle update for dir {} to {}'.format(left, right))
        # paths must be absolute (no tildes)
        left = os.path.expanduser(left)
        right = os.path.expanduser(right)
        if self._ignore([left, right]):
            return True
        # find the differences
        diff = filecmp.dircmp(left, right, ignore=None)
        # handle directories diff
        return self._merge_dirs(diff)

    def _merge_dirs(self, diff):
        """Synchronize directories recursively."""
        left, right = diff.left, diff.right
        if self.debug:
            self.log.dbg('sync dir {} to {}'.format(left, right))
        if self._ignore([left, right]):
            return True

        # create dirs that don't exist in dotdrop
        for toadd in diff.left_only:
            exist = os.path.join(left, toadd)
            if not os.path.isdir(exist):
                # ignore files for now
                continue
            # match to dotdrop dotpath
            new = os.path.join(right, toadd)
            if self._ignore([exist, new]):
                continue
            if self.dry:
                self.log.dry('would cp -r {} {}'.format(exist, new))
                continue
            if self.debug:
                self.log.dbg('cp -r {} {}'.format(exist, new))
            # Newly created directory should be copied as is (for efficiency).
            shutil.copytree(exist, new)

        # remove dirs that don't exist in deployed version
        for toremove in diff.right_only:
            old = os.path.join(right, toremove)
            if not os.path.isdir(old):
                # ignore files for now
                continue
            if self._ignore([old]):
                continue
            if self.dry:
                self.log.dry('would rm -r {}'.format(old))
                continue
            if self.debug:
                self.log.dbg('rm -r {}'.format(old))
            if not self._confirm_rm_r(old):
                continue
            utils.remove(old)

        # handle files diff
        # sync files that exist in both but are different
        fdiff = diff.diff_files
        fdiff.extend(diff.funny_files)
        fdiff.extend(diff.common_funny)
        for f in fdiff:
            fleft = os.path.join(left, f)
            fright = os.path.join(right, f)
            if self._ignore([fleft, fright]):
                continue
            if self.dry:
                self.log.dry('would cp {} {}'.format(fleft, fright))
                continue
            if self.debug:
                self.log.dbg('cp {} {}'.format(fleft, fright))
            self._handle_file(fleft, fright, compare=False)

        # copy files that don't exist in dotdrop
        for toadd in diff.left_only:
            exist = os.path.join(left, toadd)
            if os.path.isdir(exist):
                # ignore dirs, done above
                continue
            new = os.path.join(right, toadd)
            if self._ignore([exist, new]):
                continue
            if self.dry:
                self.log.dry('would cp {} {}'.format(exist, new))
                continue
            if self.debug:
                self.log.dbg('cp {} {}'.format(exist, new))
            shutil.copyfile(exist, new)

        # remove files that don't exist in deployed version
        for toremove in diff.right_only:
            new = os.path.join(right, toremove)
            if not os.path.exists(new):
                continue
            if os.path.isdir(new):
                # ignore dirs, done above
                continue
            if self._ignore([new]):
                continue
            if self.dry:
                self.log.dry('would rm {}'.format(new))
                continue
            if self.debug:
                self.log.dbg('rm {}'.format(new))
            utils.remove(new)

        # Recursively decent into common subdirectories.
        for subdir in diff.subdirs.values():
            self._merge_dirs(subdir)

        # Nothing more to do here.
        return True

    def _overwrite(self, src, dst):
        """ask for overwritting"""
        msg = 'Overwrite \"{}\" with \"{}\"?'.format(dst, src)
        if self.safe and not self.log.ask(msg):
            return False
        return True

    def _confirm_rm_r(self, directory):
        """ask for rm -r directory"""
        msg = 'Recursively remove \"{}\"?'.format(directory)
        if self.safe and not self.log.ask(msg):
            return False
        return True

    def _ignore(self, paths):
        if utils.must_ignore(paths, self.ignores, debug=self.debug):
            if self.debug:
                self.log.dbg('ignoring update for {}'.format(paths))
            return True
        return False

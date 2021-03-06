# -*- coding: utf-8 -*-

"""
 (c) 2015-2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""
from __future__ import print_function

import abc
import logging
import os
import pkg_resources
import subprocess

import werkzeug

import pagure
import pagure.exceptions
from pagure import APP
from pagure.lib import model

logging.config.dictConfig(APP.config.get('LOGGING') or {'version': 1})
_log = logging.getLogger(__name__)


def get_git_auth_helper(backend, *args, **kwargs):
    """ Instantiate and return the appropriate git auth helper backend.

    :arg backend: The name of the backend to find on the system (declared via
        the entry_points in setup.py).
        Pagure comes by default with the following backends:
            test_auth, gitolite2, gitolite3
    :type backend: str

    """
    _log.info('Looking for backend: %s', backend)
    points = pkg_resources.iter_entry_points('pagure.git_auth.helpers')
    classes = dict([(point.name, point) for point in points])
    _log.debug("Found the following installed helpers %r" % classes)
    cls = classes[backend].load()
    _log.debug("Instantiating helper %r from backend key %r" % (cls, backend))
    return cls(*args, **kwargs)


class GitAuthHelper(object):
    """ The class to inherit from when creating your own git authentication
    helper.
    """

    __metaclass__ = abc.ABCMeta

    @classmethod
    @abc.abstractmethod
    def generate_acls(self, project, group=None):
        """ This is the method that is called by pagure to generate the
        configuration file.

        :arg project: the project of which to update the ACLs. This argument
            can take three values: ``-1``, ``None`` and a project.
            If project is ``-1``, the configuration should be refreshed for
            *all* projects.
            If project is ``None``, there no specific project to refresh
            but the ssh key of an user was added and updated or a group
            was removed.
            If project is a pagure.lib.model.Project, the configuration of
            this project should be updated.
        :type project: None, int or pagure.lib.model.Project
        :kwarg group: the group to refresh the members of
        :type group: None or pagure.lib.model.PagureGroup

        (This behaviour is based on the workflow of gitolite, if you are
        implementing a different auth backend and need more granularity,
        feel free to let us know.)

        """
        pass

    @classmethod
    @abc.abstractmethod
    def remove_acls(self, session, project):
        """ This is the method that is called by pagure to remove a project
        from the configuration file.

        :arg cls: the current class
        :type: GitAuthHelper
        :arg session: the session with which to connect to the database
        :arg project: the project to remove from the gitolite configuration
            file.
        :type project: pagure.lib.model.Project

        """
        pass


def _read_file(filename):
    """ Reads the specified file and return its content.
    Returns None if it could not read the file for any reason.
    """
    if not os.path.exists(filename):
        _log.info('Could not find file: %s', filename)
    else:
        with open(filename) as stream:
            return stream.read()


class Gitolite2Auth(GitAuthHelper):
    """ A gitolite 2 authentication module. """

    @classmethod
    def _process_project(cls, project, config, global_pr_only):
        """ Generate the gitolite configuration for the specified project.

        :arg project: the project to generate the configuration for
        :type project: pagure.lib.model.Project
        :arg config: a list containing the different lines of the
            configuration file
        :type config: list
        :arg groups: a dictionary containing the group name as key and the
            users member of the group as values
        :type groups: dict(str: list)
        :arg global_pr_only: boolean on whether the pagure instance enforces
            the PR workflow only or not
        :type global_pr_only: bool
        :return: the updated config
        :return type: list

        """
        _log.debug('    Processing project: %s', project.fullname)

        # Check if the project or the pagure instance enforce the PR only
        # development model.
        pr_only = project.settings.get('pull_request_access_only', False)

        for repos in ['repos', 'docs/', 'tickets/', 'requests/']:
            if repos == 'repos':
                # Do not grant access to project enforcing the PR model
                if pr_only or (global_pr_only and not project.is_fork):
                    continue
                repos = ''

            config.append('repo %s%s' % (repos, project.fullname))
            if not project.private and repos not in ['tickets/', 'requests/']:
                config.append('  R   = @all')
            if project.committer_groups:
                config.append('  RW+ = @%s' % ' @'.join(
                    [
                        group.group_name
                        for group in project.committer_groups
                    ]
                ))
            config.append('  RW+ = %s' % project.user.user)
            for user in project.committers:
                # This should never be the case (that the project.user
                # is in the committers) but better safe than sorry
                if user.user != project.user.user:
                    config.append('  RW+ = %s' % user.user)
            for deploykey in project.deploykeys:
                access = 'R'
                if deploykey.pushaccess:
                    access = 'RW+'
                # Note: the replace of / with _ is because gitolite
                # users can't contain a /. At first, this might look
                # like deploy keys in a project called
                # $namespace_$project would give access to the repos of
                # a project $namespace/$project or vica versa, however
                # this is NOT the case because we add the deploykey.id
                # to the end of the deploykey name, which means it is
                # unique. The project name is solely there to make it
                # easier to determine what project created the deploykey
                # for admins.
                config.append('  %s = deploykey_%s_%s' %
                              (access,
                               werkzeug.secure_filename(project.fullname),
                               deploykey.id))
            config.append('')

        return config

    @classmethod
    def _clean_current_config(
            cls, current_config, project):
        """ Remove the specified project from the current configuration file

        :arg current_config: the content of the current/actual gitolite
            configuration file read from the disk
        :type current_config: list
        :arg project: the project to update in the configuration file
        :type project: pagure.lib.model.Project

        """
        keys = [
            'repo %s%s' % (repos, project.fullname)
            for repos in ['', 'docs/', 'tickets/', 'requests/']
        ]

        keep = True
        config = []
        for line in current_config:
            line = line.rstrip()

            if line in keys:
                keep = False
                continue

            if keep is False and line == '':
                keep = True

            if keep:
                config.append(line)

        return config

    @classmethod
    def _clean_groups(cls, config, group=None):
        """ Removes the groups in the given configuration file.

        :arg config: the current configuration
        :type config: list
        :kwarg group: the group to refresh the members of
        :type group: None or pagure.lib.model.PagureGroup
        :return: the configuration without the groups
        :return type: list

        """

        if group is None:
            output = [
                row.rstrip()
                for row in config
                if not row.startswith('@')
                and row.strip() != '# end of groups']
        else:
            end_grp = None
            seen = False
            output = []
            for idx, row in enumerate(config):
                if end_grp is None and row.startswith('repo '):
                    end_grp = idx

                if row.startswith('@%s ' % group.group_name):
                    seen = True
                    row = '@%s  = %s' % (
                        group.group_name,
                        ' '.join(sorted(
                            [user.username for user in group.users])
                        )
                    )
                output.append(row)

            if not seen:
                row = '@%s  = %s' % (
                    group.group_name,
                    ' '.join(sorted([user.username for user in group.users]))
                )
                output.insert(end_grp, '')
                output.insert(end_grp, row)

        return output

    @classmethod
    def _generate_groups_config(cls, session):
        """ Generate the gitolite configuration for all of the groups.

        :arg session: the session with which to connect to the database
        :return: the gitolite configuration for the groups
        :return type: list

        """
        query = session.query(
            model.PagureGroup
        ).order_by(
            model.PagureGroup.group_name
        )

        groups = {}
        for grp in query.all():
            groups[grp.group_name] = [user.username for user in grp.users]

        return groups

    @classmethod
    def _get_current_config(cls, configfile, preconfig=None, postconfig=None):
        """ Load the current gitolite configuration file from the disk.

        :arg configfile: the name of the configuration file to load
        :type configfile: str
        :kwarg preconf: the content of the file to include at the top of the
            gitolite configuration file, used here to determine that a part of
            the configuration file should be cleaned at the top.
        :type preconf: None or str
        :kwarg postconf: the content of the file to include at the bottom of
            the gitolite configuration file, used here to determine that a part
            of the configuration file should be cleaned at the bottom.
        :type postconf: None or str

        """
        _log.info('Reading in the current configuration: %s', configfile)
        with open(configfile) as stream:
            current_config = [line.rstrip() for line in stream]
        if current_config and current_config[-1] == '# end of body':
            current_config = current_config[:-1]

        if preconfig:
            idx = None
            for idx, row in enumerate(current_config):
                if row.strip() == '# end of header':
                    break
            if idx is not None:
                idx = idx + 1
                _log.info('Removing the first %s lines', idx)
                current_config = current_config[idx:]

        if postconfig:
            idx = None
            for idx, row in enumerate(current_config):
                if row.strip() == '# end of body':
                    break
            if idx is not None:
                _log.info(
                    'Keeping the first %s lines out of %s',
                    idx, len(current_config))
                current_config = current_config[:idx]

        return current_config

    @classmethod
    def write_gitolite_acls(
            cls, session, configfile, project, preconf=None, postconf=None,
            group=None):
        """ Generate the configuration file for gitolite for all projects
        on the forge.

        :arg cls: the current class
        :type: Gitolite2Auth
        :arg session: a session to connect to the database with
        :arg configfile: the name of the configuration file to generate/write
        :type configfile: str
        :arg project: the project to update in the gitolite configuration
            file. It can be of three types/values.
            If it is ``-1`` or if the file does not exist on disk, the
            entire gitolite configuration will be re-generated.
            If it is ``None``, the gitolite configuration will have its
            groups information updated but not the projects and will be
            re-compiled.
            If it is a ``pagure.lib.model.Project``, the gitolite
            configuration will be updated for just this project.
        :type project: None, int or spagure.lib.model.Project
        :kwarg preconf: a file to include at the top of the configuration
            file
        :type preconf: None or str
        :kwarg postconf: a file to include at the bottom of the
            configuration file
        :type postconf: None or str
        :kwarg group: the group to refresh the members of
        :type group: None or pagure.lib.model.PagureGroup

        """
        _log.info('Write down the gitolite configuration file')

        preconfig = None
        if preconf:
            _log.info(
                'Loading the file to include at the top of the generated one')
            preconfig = _read_file(preconf)

        postconfig = None
        if postconf:
            _log.info(
                'Loading the file to include at the end of the generated one')
            postconfig = _read_file(postconf)

        global_pr_only = pagure.APP.config.get('PR_ONLY', False)
        config = []
        groups = {}
        if group is None:
            groups = cls._generate_groups_config(session)

        if project == -1 or not os.path.exists(configfile):
            _log.info('Refreshing the configuration for all projects')
            query = session.query(model.Project).order_by(model.Project.id)
            for project in query.all():
                config = cls._process_project(
                    project, config, global_pr_only)
        elif project:
            _log.info('Refreshing the configuration for one project')
            config = cls._process_project(project, config, global_pr_only)

            current_config = cls._get_current_config(
                configfile, preconfig, postconfig)

            current_config = cls._clean_current_config(
                current_config, project)

            config = current_config + config

        if config:
            _log.info('Cleaning the group %s from the loaded config', group)
            config = cls._clean_groups(config, group=group)

        else:
            current_config = cls._get_current_config(
                configfile, preconfig, postconfig)

            _log.info(
                'Cleaning the group %s from the config on disk', group)
            config = cls._clean_groups(current_config, group=group)

        if not config:
            return

        _log.info('Writing the configuration to: %s', configfile)
        with open(configfile, 'w') as stream:
            if preconfig:
                stream.write(preconfig + '\n')
                stream.write('# end of header\n')

            if groups:
                for key, users in groups.iteritems():
                    stream.write('@%s  = %s\n' % (key, ' '.join(users)))
                stream.write('# end of groups\n\n')

            prev = None
            for row in config:
                if prev is None:
                    prev = row
                if prev == row == '':
                    continue
                stream.write(row + '\n')
                prev = row

            stream.write('# end of body\n')

            if postconfig:
                stream.write(postconfig + '\n')

    @classmethod
    def remove_acls(cls, session, project):
        """ Remove a project from the configuration file for gitolite.

        :arg cls: the current class
        :type: Gitolite2Auth
        :arg session: the session with which to connect to the database
        :arg project: the project to remove from the gitolite configuration
            file.
        :type project: pagure.lib.model.Project

        """
        _log.info('Remove project from the gitolite configuration file')

        if not project:
            raise RuntimeError('Project undefined')

        configfile = pagure.APP.config['GITOLITE_CONFIG']
        preconf = pagure.APP.config.get('GITOLITE_PRE_CONFIG') or None
        postconf = pagure.APP.config.get('GITOLITE_POST_CONFIG') or None

        if not os.path.exists(configfile):
            _log.info(
                'Not configuration file found at: %s... bailing' % configfile)
            return

        preconfig = None
        if preconf:
            _log.info(
                'Loading the file to include at the top of the generated one')
            preconfig = _read_file(preconf)

        postconfig = None
        if postconf:
            _log.info(
                'Loading the file to include at the end of the generated one')
            postconfig = _read_file(postconf)

        config = []
        groups = cls._generate_groups_config(session)

        _log.info('Removing the project from the configuration')

        current_config = cls._get_current_config(
            configfile, preconfig, postconfig)

        current_config = cls._clean_current_config(
            current_config, project)

        config = current_config + config

        if config:
            _log.info('Cleaning the groups from the loaded config')
            config = cls._clean_groups(config)

        else:
            current_config = cls._get_current_config(
                configfile, preconfig, postconfig)

            _log.info(
                'Cleaning the groups from the config on disk')
            config = cls._clean_groups(config)

        if not config:
            return

        _log.info('Writing the configuration to: %s', configfile)
        with open(configfile, 'w') as stream:
            if preconfig:
                stream.write(preconfig + '\n')
                stream.write('# end of header\n')

            if groups:
                for key, users in groups.iteritems():
                    stream.write('@%s  = %s\n' % (key, ' '.join(users)))
                stream.write('# end of groups\n\n')

            prev = None
            for row in config:
                if prev is None:
                    prev = row
                if prev == row == '':
                    continue
                stream.write(row + '\n')
                prev = row

            stream.write('# end of body\n')

            if postconfig:
                stream.write(postconfig + '\n')

    @staticmethod
    def _get_gitolite_command():
        """ Return the gitolite command to run based on the info in the
        configuration file.
        """
        _log.info('Compiling the gitolite configuration')
        gitolite_folder = pagure.APP.config.get('GITOLITE_HOME', None)
        if gitolite_folder:
            cmd = 'GL_RC=%s GL_BINDIR=%s gl-compile-conf' % (
                pagure.APP.config.get('GL_RC'),
                pagure.APP.config.get('GL_BINDIR')
            )
            _log.debug('Command: %s', cmd)
            return cmd

    @classmethod
    def generate_acls(cls, project, group=None):
        """ Generate the gitolite configuration file for all repos

        :arg project: the project to update in the gitolite configuration
            file. It can be of three types/values.
            If it is ``-1`` or if the file does not exist on disk, the
            entire gitolite configuration will be re-generated.
            If it is ``None``, the gitolite configuration will not be
            changed but will be re-compiled.
            If it is a ``pagure.lib.model.Project``, the gitolite
            configuration will be updated for just this project.
        :type project: None, int or pagure.lib.model.Project
        :kwarg group: the group to refresh the members of
        :type group: None or pagure.lib.model.PagureGroup

        """
        _log.info('Refresh gitolite configuration')

        if project is not None or group is not None:
            cls.write_gitolite_acls(
                pagure.SESSION,
                project=project,
                configfile=pagure.APP.config['GITOLITE_CONFIG'],
                preconf=pagure.APP.config.get('GITOLITE_PRE_CONFIG') or None,
                postconf=pagure.APP.config.get('GITOLITE_POST_CONFIG') or None,
                group=group,
            )

        cmd = cls._get_gitolite_command()
        if cmd:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=pagure.APP.config['GITOLITE_HOME']
            )
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                error_msg = (
                    'The command "{0}" failed with'
                    '\n\n  out: "{1}\n\n  err:"{2}"'
                    .format(cmd, stdout, stderr))
                raise pagure.exceptions.PagureException(error_msg)


class Gitolite3Auth(Gitolite2Auth):
    """ A gitolite 3 authentication module. """

    @staticmethod
    def _get_gitolite_command():
        """ Return the gitolite command to run based on the info in the
        configuration file.
        """
        _log.info('Compiling the gitolite configuration')
        gitolite_folder = pagure.APP.config.get('GITOLITE_HOME', None)
        if gitolite_folder:
            cmd = 'HOME=%s gitolite compile && HOME=%s gitolite trigger '\
                'POST_COMPILE' % (gitolite_folder, gitolite_folder)
            _log.debug('Command: %s', cmd)
            return cmd


class GitAuthTestHelper(GitAuthHelper):
    """ Simple test auth module to check the auth customization system. """

    @classmethod
    def generate_acls(cls, project, group=None):
        """ Print a statement when called, useful for debugging, only.

        :arg project: this variable is just printed out but not used
            in any real place.
        :type project: None, int or spagure.lib.model.Project
        :kwarg group: the group to refresh the members of
        :type group: None or pagure.lib.model.PagureGroup

        """
        out = 'Called GitAuthTestHelper.generate_acls() ' \
            'with args: project=%s, group=%s' % (project, group)
        print(out)
        return out

    @classmethod
    def remove_acls(cls, session, project):
        """ Print a statement about which a project would be removed from
        the configuration file for gitolite.

        :arg cls: the current class
        :type: GitAuthHelper
        :arg session: the session with which to connect to the database
        :arg project: the project to remove from the gitolite configuration
            file.
        :type project: pagure.lib.model.Project

        """

        out = 'Called GitAuthTestHelper.remove_acls() ' \
            'with args: project=%s' % (project.fullname)
        print(out)
        return out

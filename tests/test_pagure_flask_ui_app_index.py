# -*- coding: utf-8 -*-

"""
 (c) 2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

__requires__ = ['SQLAlchemy >= 0.8']
import pkg_resources

import datetime
import unittest
import shutil
import sys
import os

import six
import json
import pygit2
from mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pagure.lib
import tests


class PagureFlaskAppIndextests(tests.Modeltests):
    """ Tests for the index page of flask app controller of pagure """

    def setUp(self):
        """ Set up the environnment, ran before every tests. """
        super(PagureFlaskAppIndextests, self).setUp()

        pagure.APP.config['TESTING'] = True
        pagure.SESSION = self.session
        pagure.ui.SESSION = self.session
        pagure.ui.app.SESSION = self.session
        pagure.ui.filters.SESSION = self.session
        pagure.ui.repo.SESSION = self.session

    @patch.dict('pagure.APP.config', {'HTML_TITLE': 'Pagure HTML title set'})
    def test_index_html_title(self):
        """ Test the index endpoint with a set html title. """

        output = self.app.get('/')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Home - Pagure HTML title set</title>',
            output.data)

    def test_index_logged_out(self):
        """ Test the index endpoint when logged out. """

        output = self.app.get('/')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Home - Pagure</title>', output.data)
        self.assertIn(
            '<h2 class="m-b-1">All Projects '
            '<span class="label label-default">0</span></h2>', output.data)

        tests.create_projects(self.session)

        output = self.app.get('/?page=abc')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<h2 class="m-b-1">All Projects '
            '<span class="label label-default">3</span></h2>', output.data)

    def test_index_logged_in(self):
        """ Test the index endpoint when logged in. """
        tests.create_projects(self.session)

        # Add a 3rd project with a long description
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/?repopage=abc&forkpage=def')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_commit_access_while_admin(self):
        """ Test the index endpoint filter for commit access only when user
        is an admin. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=commit')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with admin level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='admin')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After
            output = self.app.get('/?acl=commit')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">2</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_commit_access_while_commit(self):
        """ Test the index endpoint filter for commit access only when user
        is an committer. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=commit')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with commit level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='commit')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After
            output = self.app.get('/?acl=commit')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">2</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_commit_access_while_ticket(self):
        """ Test the index endpoint filter for commit access only when user
        is has ticket access. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=ticket')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with ticket level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='ticket')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After  -  projects with ticket access aren't shown
            output = self.app.get('/?acl=ticket')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_admin_access_while_commit(self):
        """ Test the index endpoint filter for admin access only when user
        is an admin. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with commit level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='admin')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After
            output = self.app.get('/?acl=admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">2</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_admin_access_while_commit(self):
        """ Test the index endpoint filter for admin access only when user
        is an committer. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with commit level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='commit')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After
            output = self.app.get('/?acl=admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

    def test_index_main_admin_access_while_commit(self):
        """ Test the index endpoint filter for main admin access only when
        user is an committer. """
        tests.create_projects(self.session)

        # Add a 3rd project just for foo
        item = pagure.lib.model.Project(
            user_id=2,  # foo
            name='test3',
            description='test project #3 with a very long description',
            hook_token='aaabbbeeefff',
        )
        self.session.add(item)
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            # Before
            output = self.app.get('/?acl=main admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)

            # Add foo to test with commit level
            project = pagure.lib._get_project(self.session, 'test')
            msg = pagure.lib.add_user_to_project(
                self.session,
                project=project,
                new_user='foo',
                user='pingou',
                access='commit')
            self.session.commit()
            self.assertEqual(msg, 'User added')

            # After
            output = self.app.get('/?acl=main admin')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Projects <span class="label label-default">1</span>',
                output.data)
            self.assertIn(
                'Forks <span class="label label-default">0</span>',
                output.data)
            self.assertEqual(
                output.data.count('<p>No group found</p>'), 1)
            self.assertEqual(
                output.data.count('<div class="card-header">'), 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)

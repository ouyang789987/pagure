# -*- coding: utf-8 -*-

"""
 (c) 2015 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

API namespace version 0.

"""

import functools

import flask

API = flask.Blueprint('api_ns', __name__, url_prefix='/api/0')


from pagure import __api_version__, APP, SESSION
import pagure
import pagure.lib


def api_login_required(f, acls=None):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        print args, kwargs
        token = None
        token_str = None
        apt_login = None
        if 'Authorization' in flask.request.headers:
            authorization = flask.request.headers['Authorization']
            if 'token' in authorization:
                token_str = authorization.split('token')[1]

        token_auth = False
        if token_str:
            token = pagure.lib.get_api_token(SESSION, token_str)
            if token and not token.expired:
                token_auth = True
                flask.g.user = token.user
                print token.acls
                print 'Add check for token ACLs'

        if not token_auth:
            output = {
                "output": "notok",
                "error": "Login invalid/expired. "
                         "Please visit %s get or renew your API token." % (
                         APP.config['APP_URL']),
            }
            jsonout = flask.jsonify(output)
            jsonout.status_code = 401
            return jsonout
        return f(*args, **kwargs)
    return decorated_function


@API.route('/version/')
@API.route('/version')
def api_version():
    '''
    API Version
    -----------
    Display the most recent api version.

    ::

        /api/version

    Accepts GET queries only.

    Sample response:

    ::

        {
          "version": "1"
        }

    '''
    return flask.jsonify({'version': __api_version__})


@API.route('/users/')
@API.route('/users')
def api_users():
    '''
    List users
    -----------
    Returns the list of all users that have logged into this pagure instances.
    This can then be used as input for autocompletion in some forms/fields.

    ::

        /api/users

    Accepts GET queries only.

    Sample response:

    ::

        {
          "users": ["user1", "user2"]
        }

    '''
    pattern = flask.request.args.get('pattern', None)
    if pattern is not None and not pattern.endswith('*'):
        pattern += '*'

    return flask.jsonify(
        {
            'users': [
                user.username
                for user in pagure.lib.search_user(
                    SESSION, pattern=pattern)
            ]
        }
    )


@API.route('/<repo>/tags')
@API.route('/<repo>/tags/')
@API.route('/fork/<username>/<repo>/tags')
@API.route('/fork/<username>/<repo>/tags/')
def api_project_tags(repo, username=None):
    '''
    List all the tags of a project
    ------------------------------
    Returns the list of all tags of the specified project.

    ::

        /api/<repo>/tags

        /api/fork/<username>/<repo>/tags

    Accepts GET queries only.

    Sample response:

    ::

        {
          "tags": ["tag1", "tag2"]
        }

    '''
    pattern = flask.request.args.get('pattern', None)
    if pattern is not None and not pattern.endswith('*'):
        pattern += '*'

    project = pagure.lib.get_project(SESSION, repo, username)
    if not project:
        output = {'output': 'notok', 'error': 'Project not found'}
        jsonout = flask.jsonify(output)
        jsonout.status_code = 404
        return jsonout

    return flask.jsonify(
        {
            'tags': [
                tag.tag
                for tag in pagure.lib.get_tags_of_project(
                    SESSION, project, pattern=pattern)
            ]
        }
    )


@API.route('/groups/')
@API.route('/groups')
def api_groups():
    '''
    List groups
    -----------
    Returns the list of all groups present on this pagure instance
    This can then be used as input for autocompletion in some forms/fields.

    ::

        /api/groups

    Accepts GET queries only.

    Sample response:

    ::

        {
          "groups": ["group1", "group2"]
        }

    '''
    pattern = flask.request.args.get('pattern', None)
    if pattern is not None and not pattern.endswith('*'):
        pattern += '*'

    return flask.jsonify(
        {
            'groups': [
                group.group_name
                for group in pagure.lib.search_groups(
                    SESSION, pattern=pattern)
            ]
        }
    )
